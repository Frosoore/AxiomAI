"""tests/test_runtime_check.py

GUI-layer warning when torch's native runtime can't load (ui/runtime_check.py).
The dialog is mocked so the suite never blocks on a modal.
"""

import sys

import pytest

from ui import runtime_check


def test_status_never_raises_and_is_known():
    assert runtime_check.embedding_runtime_status() in ("ok", "missing_dll", "not_installed")


def test_noop_when_runtime_ok(monkeypatch):
    monkeypatch.setattr(runtime_check, "embedding_runtime_status", lambda: "ok")
    monkeypatch.setattr(sys, "platform", "win32")
    assert runtime_check.maybe_warn_missing_runtime() is False


def test_noop_off_windows(monkeypatch):
    # Even with a broken runtime, non-Windows never shows the VC++ dialog.
    monkeypatch.setattr(runtime_check, "embedding_runtime_status", lambda: "missing_dll")
    monkeypatch.setattr(sys, "platform", "linux")
    assert runtime_check.maybe_warn_missing_runtime() is False


def test_noop_when_torch_simply_absent(monkeypatch):
    # 'not_installed' is a different problem — don't blame the VC++ redist.
    monkeypatch.setattr(runtime_check, "embedding_runtime_status", lambda: "not_installed")
    monkeypatch.setattr(sys, "platform", "win32")
    assert runtime_check.maybe_warn_missing_runtime() is False


def _install_fake_box(monkeypatch, *, clicked_is_download: bool):
    """Replace QMessageBox with a non-blocking fake; return a state dict."""
    state = {"shown": 0, "opened_url": None}

    class _FakeBox:
        # Enum members the real code references.
        Warning = AcceptRole = RejectRole = object()

        def __init__(self, *a, **k):
            self._download = object()
            self._buttons = 0
        def setIcon(self, *a): pass
        def setWindowTitle(self, *a): pass
        def setText(self, *a): pass
        def addButton(self, *a):
            # First call = the Download button (what the code keeps a ref to).
            self._buttons += 1
            return self._download if self._buttons == 1 else object()
        def setCheckBox(self, cb): self._cb = cb
        def exec(self): state["shown"] += 1
        def clickedButton(self): return self._download if clicked_is_download else None

    import PySide6.QtWidgets as W
    monkeypatch.setattr(W, "QMessageBox", _FakeBox)

    import PySide6.QtGui as G
    monkeypatch.setattr(G.QDesktopServices, "openUrl",
                        staticmethod(lambda url: state.__setitem__("opened_url", url.toString())))
    return state


def test_shows_once_and_respects_marker(monkeypatch, tmp_path, qtbot):
    monkeypatch.setattr(runtime_check, "embedding_runtime_status", lambda: "missing_dll")
    monkeypatch.setattr(sys, "platform", "win32")
    marker = tmp_path / "marker"
    monkeypatch.setattr(runtime_check, "_marker_path", lambda: marker)
    state = _install_fake_box(monkeypatch, clicked_is_download=False)

    # Checkbox unchecked by default → shown, no marker, no URL opened.
    assert runtime_check.maybe_warn_missing_runtime() is True
    assert state["shown"] == 1
    assert not marker.exists()

    # Once the user dismisses for good, the marker silences future launches.
    marker.write_text("dismissed\n", encoding="utf-8")
    assert runtime_check.maybe_warn_missing_runtime() is False
    assert state["shown"] == 1  # not shown again


def test_download_button_opens_microsoft_url(monkeypatch, tmp_path, qtbot):
    monkeypatch.setattr(runtime_check, "embedding_runtime_status", lambda: "missing_dll")
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(runtime_check, "_marker_path", lambda: tmp_path / "marker")
    state = _install_fake_box(monkeypatch, clicked_is_download=True)

    assert runtime_check.maybe_warn_missing_runtime() is True
    assert state["opened_url"] == runtime_check._VC_REDIST_URL
