import json
import urllib.request
import re
from pathlib import Path
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextBrowser, QHBoxLayout, QTextEdit, QPushButton
from PySide6.QtGui import QTextCursor, QTextCharFormat, QTextBlockFormat, QColor, QFont, QKeyEvent, QImage, QTextDocument
from PySide6.QtCore import Signal, QUrl, Qt

from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from core.localization import tr

class _RichTextBrowser(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._image_cache = {}
        self._nam = QNetworkAccessManager(self)
        self._pending_urls = set()
        # Use a transparent placeholder initially to prevent layout jumps
        self._placeholder = QImage(1, 1, QImage.Format_ARGB32)
        self._placeholder.fill(Qt.transparent)

    def loadResource(self, resource_type: int, url: QUrl):
        if resource_type == QTextDocument.ImageResource:
            url_str = url.toString()
            if url_str in self._image_cache:
                return self._image_cache[url_str]
            
            if url.scheme() in ("http", "https"):
                if url_str not in self._pending_urls:
                    self._pending_urls.add(url_str)
                    self._async_fetch(url)
                # Return placeholder while loading
                return self._placeholder
                
        return super().loadResource(resource_type, url)

    def _async_fetch(self, url: QUrl):
        request = QNetworkRequest(url)
        request.setAttribute(QNetworkRequest.Attribute.CacheLoadControlAttribute, QNetworkRequest.CacheLoadControl.PreferCache)
        reply = self._nam.get(request)
        reply.finished.connect(lambda: self._on_fetch_finished(reply))

    def _on_fetch_finished(self, reply: QNetworkReply):
        url_str = reply.url().toString()
        if reply.error() == QNetworkReply.NetworkError.NoError:
            data = reply.readAll()
            image = QImage.fromData(data)
            if not image.isNull():
                self._image_cache[url_str] = image
                # Update the document resource cache
                self.document().addResource(QTextDocument.ImageResource, reply.url(), image)
                # Trigger a re-layout to show the image
                self.setLineWrapColumnOrWidth(self.lineWrapColumnOrWidth())
        else:
            # Mark as broken to avoid re-fetching
            self._image_cache[url_str] = self._placeholder
            
        if url_str in self._pending_urls:
            self._pending_urls.remove(url_str)
        reply.deleteLater()


class _MultiLineInput(QTextEdit):
    submit_requested = Signal()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (event.modifiers() & Qt.ShiftModifier):
            self.submit_requested.emit()
        else:
            super().keyPressEvent(event)

class ChatDisplayWidget(QWidget):
    variant_requested = Signal(int, int)
    regenerate_requested = Signal(int)
    message_submitted = Signal(str)
    edit_message_requested = Signal(str, int)

    
    # Tool-call fences hidden during streaming. The engine parser
    # (axiom/backends/base.py::_FENCE_PATTERNS) accepts ~~~json AND ```json —
    # the models (Gemini notably) often use backticks despite the prompt, so
    # the UI filter must know both or the raw JSON leaks into the chat.
    _JSON_FENCES = (("~~~json", "~~~"), ("```json", "```"))

    _IMG_REGEX = re.compile(
        r'!\[.*?\]\((https?://[^\)]+)\)'              # ![alt](url)
        r'|\[.*?\]\((https?://[^\)]+\.(?:png|jpg|jpeg|gif|webp))\)' # [alt](url to image)
        r'|<img[^>]+src=[\'"](https?://[^\'"]+)[\'"]' # <img src="url">
        r'|(?<![\("])(https?://\S+\.(?:png|jpg|jpeg|gif|webp))\b', # bare url
        re.IGNORECASE
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)

        # Use our custom browser to fetch HTTP images
        self._narrative_display = _RichTextBrowser()
        self._narrative_display.setReadOnly(True)
        self._narrative_display.setUndoRedoEnabled(False)
        self._narrative_display.document().setMaximumBlockCount(1000)
        self._narrative_display.setOpenLinks(False)
        self._narrative_display.anchorClicked.connect(self._on_link_clicked)

        from axiom.config import load_config
        cfg = load_config()

        font = self._narrative_display.font()
        font.setPointSize(cfg.ui_font_size)
        self._narrative_display.setFont(font)

        self._layout.addWidget(self._narrative_display)
        
        # Pre-cache text formats for performance
        self._formats = {}
        for bold in [False, True]:
            for italic in [False, True]:
                fmt = QTextCharFormat()
                if italic:
                    fmt.setForeground(QColor("#9EADC8"))
                    fmt.setFontItalic(True)
                else:
                    fmt.setForeground(QColor("#E0E0E0"))
                    fmt.setFontItalic(False)
                if bold:
                    fmt.setFontWeight(QFont.Weight.Bold)
                else:
                    fmt.setFontWeight(QFont.Weight.Normal)
                self._formats[(bold, italic)] = fmt

        from ui.help_system import doc
        doc(self._narrative_display, "tabletop.chat_log")

        # Input row
        input_row = QHBoxLayout()
        self._input_box = doc(_MultiLineInput(), "tabletop.chat_input")
        self._input_box.setFixedHeight(60)
        self._input_box.setPlaceholderText(tr("type_message"))
        self._send_button = doc(QPushButton(tr("send")), "tabletop.send")
        self._send_button.setFixedWidth(90)
        self._send_button.setFixedHeight(60)
        input_row.addWidget(self._input_box)
        input_row.addWidget(self._send_button)
        self._layout.addLayout(input_row)

        self._send_button.clicked.connect(self._on_send_clicked)
        self._input_box.submit_requested.connect(self._on_send_clicked)

        self._reset_states()
        self._in_json_fence = False
        self._json_fence_close = "~~~"
        self._token_buf = ""
        # Document range [start, end] of a "generating illustration…" placeholder,
        # or None when no placeholder is currently shown. Stored as an explicit
        # range (not "to end") because the final token flush may append narrative
        # text *after* the placeholder before we replace it.
        self._img_placeholder_range: tuple[int, int] | None = None

    def retranslate_ui(self):
        self._input_box.setPlaceholderText(tr("type_message"))
        self._send_button.setText(tr("send"))

    def set_send_enabled(self, enabled: bool):
        self._send_button.setEnabled(enabled)
        self._input_box.setEnabled(enabled)

    def update_font_size(self, size: int):
        """Update the font size dynamically without restarting."""
        font = self._narrative_display.font()
        font.setPointSize(size)
        self._narrative_display.setFont(font)
        self._narrative_display.document().setDefaultFont(font)

    def _on_send_clicked(self):
        text = self._input_box.toPlainText().strip()
        if not text:
            return
        self._input_box.clear()
        self.message_submitted.emit(text)

    def _reset_states(self):
        self._is_italic = False
        self._is_bold = False
        self._asterisk_buffer = 0
        self._just_closed_action = False
        
        cursor = self._narrative_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("#E0E0E0"))
        fmt.setFontItalic(False)
        fmt.setFontWeight(QFont.Weight.Normal)
        self._narrative_display.setCurrentCharFormat(fmt)

    def _on_link_clicked(self, url: QUrl):
        url_str = url.toString()
        if url_str.startswith("variant:"):
            parts = url_str.split(":")
            if len(parts) == 3:
                self.variant_requested.emit(int(parts[1]), int(parts[2]))
        elif url_str.startswith("regenerate:"):
            parts = url_str.split(":")
            if len(parts) == 2:
                self.regenerate_requested.emit(int(parts[1]))
        elif url_str.startswith("edit:"):
            parts = url_str.split(":")
            if len(parts) == 3:
                self.edit_message_requested.emit(parts[1], int(parts[2]))


    def begin_turn(self, turn_id: int = None):
        self._reset_states()
        self._in_json_fence = False
        self._token_buf = ""

    def clear_after_turn_id(self, turn_id: int = None):
        pass

    def append_user_message(self, text: str, turn_id: int | None = None):
        cursor = self._narrative_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("#4FC1FF"))
        fmt.setFontWeight(QFont.Weight.Bold)
        
        prefix = "" if cursor.position() == 0 else "\n\n"
        cursor.insertText(f"{prefix}{text}", fmt)
        
        if turn_id is not None:
            edit_text = tr("edit")
            cursor.insertHtml(f" <a href='edit:user_input:{turn_id}' style='color: #555555; text-decoration: none; font-size: 8pt;'>[{edit_text}]</a>")
            
        cursor.insertText("\n\n")
        self._reset_states()

    def append_hero_intent(self, text: str, turn_id: int | None = None):
        """Display the AI Hero's intended action in a distinct style."""
        cursor = self._narrative_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        
        # Header "HERO INTENT"
        header_fmt = QTextCharFormat()
        header_fmt.setForeground(QColor("#FFB000")) # Amber
        header_fmt.setFontWeight(QFont.Weight.Bold)
        cursor.insertText("[HERO INTENT]: ", header_fmt)
        
        # The intent text itself
        text_fmt = QTextCharFormat()
        text_fmt.setForeground(QColor("#FFD54F")) # Light Amber
        text_fmt.setFontItalic(True)
        cursor.insertText(f"{text}", text_fmt)
        
        if turn_id is not None:
            edit_text = tr("edit")
            cursor.insertHtml(f" <a href='edit:hero_intent:{turn_id}' style='color: #555555; text-decoration: none; font-size: 8pt;'>[{edit_text}]</a>")
            
        cursor.insertText("\n\n")
        self._reset_states()


    def append_assistant_separator(self):
        self._reset_states()
        cursor = self._narrative_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("#E0E0E0"))
        fmt.setFontItalic(False)
        fmt.setFontWeight(QFont.Weight.Normal)
        cursor.insertText("\n-------\n", fmt)
        self._narrative_display.setTextCursor(cursor)

    def append_token(self, token: str):
        self._token_buf += token
        visible = self._flush_token_buffer()
        if visible:
            self._insert_instant_parsed_text(visible)

    def _flush_token_buffer(self, force=False) -> str:
        """Process `_token_buf` and return only the player-visible portion."""
        out_parts: list[str] = []
        buf = self._token_buf

        while buf:
            if self._in_json_fence:
                # Waiting for the closing fence matching the opener (~~~ or ```)
                close_pos = buf.find(self._json_fence_close)
                if close_pos == -1:
                    # Not yet found - keep everything buffered
                    break
                # Consume through the close fence (and any trailing newline)
                after_close = close_pos + len(self._json_fence_close)
                if after_close < len(buf) and buf[after_close] == "\n":
                    after_close += 1
                buf = buf[after_close:]
                self._in_json_fence = False
            else:
                # Earliest opener of any known fence style wins
                open_pos = -1
                opener_len = 0
                for fence_open, fence_close in self._JSON_FENCES:
                    pos = buf.find(fence_open)
                    if pos != -1 and (open_pos == -1 or pos < open_pos):
                        open_pos = pos
                        opener_len = len(fence_open)
                        self._json_fence_close = fence_close
                if open_pos == -1:
                    # No complete fence ahead.
                    if force:
                        out_parts.append(buf)
                        buf = ""
                        break

                    overlap = 0
                    for fence_open, _ in self._JSON_FENCES:
                        for length in range(len(fence_open) - 1, 0, -1):
                            if buf.endswith(fence_open[:length]):
                                overlap = max(overlap, length)
                                break

                    safe_len = len(buf) - overlap
                    out_parts.append(buf[:safe_len])
                    buf = buf[safe_len:]
                    break
                # Flush everything before the fence opener
                out_parts.append(buf[:open_pos])
                buf = buf[open_pos + opener_len:]
                self._in_json_fence = True

        self._token_buf = buf
        return "".join(out_parts)

    def flush_final_buffer(self):
        visible = self._flush_token_buffer(force=True)
        if visible:
            self._insert_instant_parsed_text(visible)

    def _get_current_format(self):
        return self._formats.get((self._is_bold, self._is_italic), self._formats[(False, False)])

    def _process_text_to_cursor(self, text: str, cursor: QTextCursor):
        for char in text:
            if char == '*':
                self._asterisk_buffer += 1
                continue
            
            if self._asterisk_buffer > 0:
                if self._asterisk_buffer == 1:
                    self._is_italic = not self._is_italic
                    self._just_closed_action = not self._is_italic
                elif self._asterisk_buffer == 2:
                    self._is_bold = not self._is_bold
                elif self._asterisk_buffer >= 3:
                    self._is_italic = not self._is_italic
                    self._is_bold = not self._is_bold
                else:
                    fmt = self._get_current_format()
                    cursor.insertText('*' * self._asterisk_buffer, fmt)
                self._asterisk_buffer = 0

            if self._just_closed_action and char in ['"', '«', '“']:
                cursor.insertText('\n')
            
            if char.strip():
                self._just_closed_action = False

            fmt = self._get_current_format()
            cursor.insertText(char, fmt)

    def _insert_instant_parsed_text(self, text: str):
        # Fix: Unescape literal \r\n and other common JSON escapes that might be in the source
        text = text.replace("\\r\\n", "\n").replace("\\n", "\n").replace('\\"', '"')
        
        cursor = self._narrative_display.textCursor()
        cursor.movePosition(QTextCursor.End)

        last_idx = 0
        for match in self._IMG_REGEX.finditer(text):
            prefix = text[last_idx:match.start()]
            if prefix:
                self._process_text_to_cursor(prefix, cursor)
                
            url = next((g for g in match.groups() if g is not None), None)
            if url:
                # Insert the image centered
                cursor.insertBlock()
                img_fmt = QTextBlockFormat()
                img_fmt.setAlignment(Qt.AlignCenter)
                cursor.insertBlock(img_fmt)
                cursor.insertHtml(f"<img src='{url}' width='400'>")
                
                # Reset block format back to normal
                reset_fmt = QTextBlockFormat()
                reset_fmt.setAlignment(Qt.AlignLeft)
                cursor.insertBlock(reset_fmt)
                self._narrative_display.setCurrentCharFormat(self._get_current_format())
                
            last_idx = match.end()

        suffix = text[last_idx:]
        if suffix:
            self._process_text_to_cursor(suffix, cursor)

    def append_variants_nav(self, turn_id: int, active_index: int, total_variants: int, is_latest: bool = False):
        cursor = self._narrative_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        
        nav_parts = []
        if total_variants > 1:
            for i in range(total_variants):
                if i == active_index:
                    nav_parts.append(f"<span style='color: #666666;'>[{i+1}]</span>")
                else:
                    nav_parts.append(f"<a href='variant:{turn_id}:{i}' style='color: #4FC1FF; text-decoration: none;'>[{i+1}]</a>")
        
        # Always allow editing narrative_text if turn_id > 0
        if turn_id > 0:
            edit_text = tr("edit")
            nav_parts.append(f"<a href='edit:narrative_text:{turn_id}' style='color: #888888; text-decoration: none;'>[{edit_text}]</a>")

        if is_latest:
            reg_text = tr("regenerate")
            nav_parts.append(f"<a href='regenerate:{turn_id}' style='color: #FFB000; text-decoration: none;'>[⟳ {reg_text}]</a>")
            
        if not nav_parts:
            return

        html_nav = "&nbsp;&nbsp;".join(nav_parts)

        
        # Force a new block centered
        block_fmt = QTextBlockFormat()
        block_fmt.setAlignment(Qt.AlignCenter)
        block_fmt.setTopMargin(10)
        block_fmt.setBottomMargin(15)
        cursor.insertBlock(block_fmt)
        
        # Insert the links
        cursor.insertHtml(f"<span style='font-size: 10pt;'>{html_nav}</span>")
        
        # Restore normal left alignment for subsequent text
        reset_fmt = QTextBlockFormat()
        reset_fmt.setAlignment(Qt.AlignLeft)
        reset_fmt.setTopMargin(0)
        reset_fmt.setBottomMargin(0)
        cursor.insertBlock(reset_fmt)
        
        self._reset_states()

    def rebuild_from_history(self, history: list[dict], assets_dir: str | Path | None = None):
        self._narrative_display.viewport().setUpdatesEnabled(False)
        try:
            self._narrative_display.clear()
            self._reset_states()
            self._token_buf = ""
            self._in_json_fence = False

            max_tid = max((e.get('turn_id', 0) for e in history), default=0)

            for event in history:
                evt_type = event.get('event_type')
                payload = event.get('payload', '')
                turn_id = event.get('turn_id', 0)

                if evt_type == 'user_input':
                    text_payload = payload.get("text", "") if isinstance(payload, dict) else str(payload)
                    self.append_user_message(text_payload, turn_id=turn_id)
                elif evt_type == 'hero_intent':
                    text_payload = payload.get("text", "") if isinstance(payload, dict) else str(payload)
                    self.append_hero_intent(text_payload, turn_id=turn_id)

                elif evt_type == 'narrative_text':
                    active_idx = 0
                    total_vars = 1
                    text_to_print = ""

                    if isinstance(payload, dict):
                         if 'active' in payload and 'variants' in payload:
                            # It's a multiverse payload
                            active_idx = payload['active']
                            variants = payload['variants']
                            total_vars = len(variants)
                            if 0 <= active_idx < total_vars:
                                text_to_print = variants[active_idx]
                         else:
                            # It's a simple dict (maybe from older schema)
                            text_to_print = payload.get("text", str(payload))
                    elif isinstance(payload, str):
                        # Simple text
                        text_to_print = payload
                    else:
                        text_to_print = str(payload)

                    self.append_assistant_separator()
                    self._insert_instant_parsed_text(text_to_print)

                    # If assets_dir is provided, check if a generated image exists for this turn_id
                    if assets_dir:
                        img_path = Path(assets_dir) / f"turn_{turn_id}.png"
                        if img_path.exists():
                            cursor = self._narrative_display.textCursor()
                            cursor.movePosition(QTextCursor.End)
                            cursor.insertBlock()
                            img_fmt = QTextBlockFormat()
                            img_fmt.setAlignment(Qt.AlignCenter)
                            cursor.insertBlock(img_fmt)
                            file_url = QUrl.fromLocalFile(str(img_path.resolve())).toString()
                            cursor.insertHtml(f"<img src='{file_url}' width='400'>")
                            
                            # Reset block format back to normal
                            reset_fmt = QTextBlockFormat()
                            reset_fmt.setAlignment(Qt.AlignLeft)
                            cursor.insertBlock(reset_fmt)
                            self._narrative_display.setCurrentCharFormat(self._get_current_format())

                    is_latest = (turn_id == max_tid)
                    self.append_variants_nav(turn_id, active_idx, total_vars, is_latest=is_latest)
            
            self._reset_states()
        finally:
            self._narrative_display.viewport().setUpdatesEnabled(True)
            self._narrative_display.verticalScrollBar().setValue(
                self._narrative_display.verticalScrollBar().maximum()
            )

    def show_image_placeholder(self):
        """Insert an inline 'generating illustration…' vignette at the end.

        Shown while the cloud backend produces the turn's image, then replaced by
        the real image (append_image) or removed (clear_image_placeholder).
        """
        if self._img_placeholder_range is not None:
            return  # already showing one
        cursor = self._narrative_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        start = cursor.position()

        block_fmt = QTextBlockFormat()
        block_fmt.setAlignment(Qt.AlignCenter)
        block_fmt.setTopMargin(10)
        block_fmt.setBottomMargin(10)
        cursor.insertBlock(block_fmt)
        cursor.insertHtml(
            f"<span style='color:#8A93A6; font-style:italic;'>🖼 {tr('generating_image')}</span>"
        )
        self._img_placeholder_range = (start, cursor.position())
        self._reset_states()
        self._narrative_display.verticalScrollBar().setValue(
            self._narrative_display.verticalScrollBar().maximum()
        )

    def clear_image_placeholder(self):
        """Remove the 'generating illustration…' vignette if present.

        Removes exactly the placeholder's range; any narrative text appended
        after it (final buffer flush) is preserved.
        """
        if self._img_placeholder_range is None:
            return
        start, end = self._img_placeholder_range
        self._img_placeholder_range = None
        cursor = self._narrative_display.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
        self._reset_states()

    def append_image(self, image_path: str | Path | None):
        # An image arrived: drop any "generating…" vignette first.
        self.clear_image_placeholder()
        if not image_path:
            return
        img_path = Path(image_path)
        if not img_path.exists():
            return

        cursor = self._narrative_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        
        cursor.insertBlock()
        img_fmt = QTextBlockFormat()
        img_fmt.setAlignment(Qt.AlignCenter)
        cursor.insertBlock(img_fmt)
        
        file_url = QUrl.fromLocalFile(str(img_path.resolve())).toString()
        cursor.insertHtml(f"<img src='{file_url}' width='400'>")
        
        # Reset block format back to normal
        reset_fmt = QTextBlockFormat()
        reset_fmt.setAlignment(Qt.AlignLeft)
        cursor.insertBlock(reset_fmt)
        self._narrative_display.setCurrentCharFormat(self._get_current_format())
        
        # Scroll to bottom
        self._narrative_display.verticalScrollBar().setValue(
            self._narrative_display.verticalScrollBar().maximum()
        )
