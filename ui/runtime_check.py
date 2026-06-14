"""ui/runtime_check.py — GUI-only warning when the embedding runtime can't load.

Lives in the UI layer on purpose: the engine (``axiom/``) stays Qt-free and just
degrades silently to a no-op semantic memory (``axiom/memory.py``). This module
turns that silent degradation into a visible, actionable dialog for the user.

The typical cause is Windows-specific: ``torch`` installs fine via pip, but its
native DLLs (``torch_python.dll`` & co.) need the **Microsoft Visual C++
Redistributable**. Without it the import raises ``OSError`` (WinError 126). A
system component like that cannot ship in ``requirements.txt`` (pip only installs
Python packages), so we point the user at the free installer instead.
"""

from __future__ import annotations

import sys

# Official Microsoft permalink to the latest x64 VC++ Redistributable.
_VC_REDIST_URL = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
_MARKER_NAME = "vcredist_warning_dismissed"


def embedding_runtime_status() -> str:
    """Return the load state of torch's native runtime.

    Returns:
        ``"ok"`` if torch imports; ``"missing_dll"`` if it is installed but its
        native libraries fail to load (the VC++ Redistributable case);
        ``"not_installed"`` if torch is absent.
    """
    try:
        import torch  # noqa: F401
        return "ok"
    except OSError:        # WinError 126: a dependent DLL is missing
        return "missing_dll"
    except Exception:      # ImportError / anything else: treat as absent
        return "not_installed"


def _marker_path():
    from axiom.paths import CONFIG_DIR
    return CONFIG_DIR / _MARKER_NAME


def maybe_warn_missing_runtime(parent=None) -> bool:
    """On Windows, warn (once) when torch's native libraries fail to load.

    No-op when: not on Windows, the runtime loads fine, torch is simply absent
    (a different problem), or the user already ticked "don't remind me again".
    Best-effort and never raises — a warning dialog must not break startup.

    Returns:
        True if the dialog was shown, False otherwise.
    """
    try:
        if sys.platform != "win32":
            return False
        if embedding_runtime_status() != "missing_dll":
            return False
        marker = _marker_path()
        if marker.exists():
            return False

        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtWidgets import QCheckBox, QMessageBox

        from core.localization import tr

        box = QMessageBox(parent)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(tr("vcredist_title"))
        box.setText(tr("vcredist_body"))
        download_btn = box.addButton(tr("vcredist_download"), QMessageBox.AcceptRole)
        box.addButton(tr("vcredist_later"), QMessageBox.RejectRole)
        dont_remind = QCheckBox(tr("vcredist_dont_remind"))
        box.setCheckBox(dont_remind)
        box.exec()

        if box.clickedButton() is download_btn:
            QDesktopServices.openUrl(QUrl(_VC_REDIST_URL))
        if dont_remind.isChecked():
            try:
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text("dismissed\n", encoding="utf-8")
            except OSError:
                pass
        return True
    except Exception:  # noqa: BLE001 — a help dialog must never crash launch
        return False
