"""tests/test_kernel_creator_safety.py

LLM mod creator, scaffold and tester (review 2026-10-03, 1-NOYAU I9, I10, m7, m8;
4-DOC I5):
- nothing generated runs before confirmation (no main.py import, no pytest);
- file paths leaving the preparation folder are refused, nothing written;
- one public catalogue of hooks/slots used by the scaffold, the prompt and the tester;
- tests run in apply_generated_mod (after "yes"); failure -> nothing installed;
- the installed folder is replaced cleanly;
- PySide6 imports are forbidden without a UI dependency.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from axiom.backends.base import LLMBackend, LLMMessage, LLMResponse
from axiom.kernel.api import PUBLIC_HOOKS, PUBLIC_SLOTS
from axiom.kernel.llm_creator import (
    ModTestsFailedError,
    apply_generated_mod,
    build_system_prompt,
    generate_mod,
)
from axiom.kernel.manifest import parse_manifest_file
from axiom.kernel.scaffold import scaffold_mod
from axiom.kernel.tester import test_mod, validate_mod_static


class FakeLLM(LLMBackend):
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def is_available(self) -> bool:
        return True

    def complete(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        return LLMResponse(content=json.dumps(self.payload), finish_reason="stop")

    def stream_tokens(self, messages, **kwargs):
        yield json.dumps(self.payload)


def _payload(mod_id: str, marker: Path, hook: str = "axiom.step:after_step", extra_files=None) -> dict:
    files = {
        "mod.toml": f'[mod]\nid = "{mod_id}"\nversion = "0.1.0"\naxiom_api = 1\nname = "X"\n'
                    f'[contributes]\nhooks = ["{hook}"]\n',
        "main.py": (
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('main executed')\n"
            "def init(ctx):\n"
            f"    ctx.register_hook({hook!r}, lambda c: None)\n"
        ),
        "tests/test_x.py": (
            "from pathlib import Path\n"
            f"Path({str(marker) + '.pytest'!r}).write_text('tests executed')\n"
            "def test_ok():\n    assert True\n"
        ),
    }
    files.update(extra_files or {})
    return {"mod_id": mod_id, "files": files}


def test_generate_executes_nothing_before_confirmation(tmp_path):
    marker = tmp_path / "marker.txt"
    result = generate_mod(
        "x", llm_backend=FakeLLM(_payload("community.safe", marker)),
        staged_mods_base_dir=tmp_path / "staged", target_mods_dir=tmp_path / "installed",
    )
    assert result.validation_passed, result.error_report
    assert not marker.exists(), "main.py was executed before confirmation"
    assert not Path(str(marker) + ".pytest").exists(), "tests were executed before confirmation"
    assert not (tmp_path / "installed" / "community.safe").exists()

    # After "yes": tests run (first execution), then install
    dest, axmod = apply_generated_mod(
        result.staged_dir, target_mods_dir=tmp_path / "installed", enable_in_config=False
    )
    assert marker.exists()
    assert dest == tmp_path / "installed" / "community.safe"
    assert axmod is not None and axmod.parent == tmp_path / "staged"


@pytest.mark.parametrize("bad_path", ["../../escaped.txt", "/tmp/abs_escape.txt", "sub/../../x.py", "C:/win.py"])
def test_paths_leaving_preparation_folder_are_refused(tmp_path, bad_path):
    payload = _payload("community.escape", tmp_path / "m", extra_files={bad_path: "pwned"})
    with pytest.raises(ValueError, match="Refused"):
        generate_mod("x", llm_backend=FakeLLM(payload), staged_mods_base_dir=tmp_path / "staged",
                     target_mods_dir=tmp_path / "installed")
    assert not (tmp_path / "escaped.txt").exists()
    assert not (tmp_path / "staged" / "community.escape").exists()


def test_unknown_hook_is_flagged_statically(tmp_path):
    result = generate_mod(
        "x", llm_backend=FakeLLM(_payload("community.ghost", tmp_path / "m", hook="axiom.time:tick")),
        staged_mods_base_dir=tmp_path / "staged", target_mods_dir=tmp_path / "installed",
    )
    assert not result.validation_passed
    assert "Unknown hook 'axiom.time:tick'" in result.error_report
    with pytest.raises(ModTestsFailedError):
        apply_generated_mod(result.staged_dir, target_mods_dir=tmp_path / "installed", enable_in_config=False)
    assert not (tmp_path / "installed" / "community.ghost").exists()


def test_failing_tests_install_nothing_and_replacement_is_clean(tmp_path):
    installed = tmp_path / "installed"
    old = installed / "community.repl"
    old.mkdir(parents=True)
    (old / "obsolete.py").write_text("x = 1\n", encoding="utf-8")
    (old / "mod.toml").write_text('[mod]\nid = "community.repl"\nversion = "0.0.1"\naxiom_api = 1\n', encoding="utf-8")

    failing = _payload("community.repl", tmp_path / "m", extra_files={"tests/test_x.py": "def test_ko():\n    assert False\n"})
    result = generate_mod("x", llm_backend=FakeLLM(failing), staged_mods_base_dir=tmp_path / "staged",
                          target_mods_dir=installed)
    assert "obsolete.py" in result.file_diffs  # the removal is part of the diff
    with pytest.raises(ModTestsFailedError):
        apply_generated_mod(result.staged_dir, target_mods_dir=installed, enable_in_config=False)
    assert (old / "obsolete.py").exists()  # untouched

    ok = _payload("community.repl", tmp_path / "m")
    result = generate_mod("x", llm_backend=FakeLLM(ok), staged_mods_base_dir=tmp_path / "staged",
                          target_mods_dir=installed)
    dest, _ = apply_generated_mod(result.staged_dir, target_mods_dir=installed, enable_in_config=False,
                                  compile_axmod=False)
    assert not (dest / "obsolete.py").exists()
    assert parse_manifest_file(dest / "mod.toml").version == "0.1.0"
    assert [p.name for p in installed.iterdir()] == ["community.repl"]  # no temp leftovers


def test_single_catalogue_drives_prompt_scaffold_and_tester(tmp_path):
    prompt = build_system_prompt()
    for name in PUBLIC_HOOKS:
        assert name in prompt
    for name in PUBLIC_SLOTS:
        assert name in prompt
    for ghost in ("axiom.turn:after_step", "axiom.turn:gather_context", "axiom.time:tick",
                  "axiom.world:rules", "first_win", "axiom.turn:execute_step"):
        assert ghost not in prompt
    assert "sandbox" not in prompt.lower()

    for mod_type in ("hook", "slot", "data"):
        dest = scaffold_mod(f"author.t{mod_type}", mod_type=mod_type, target_dir=tmp_path / mod_type)
        manifest = parse_manifest_file(dest / "mod.toml")
        for hook in manifest.contributes.hooks:
            assert hook in PUBLIC_HOOKS
        for slot in manifest.contributes.slots:
            assert slot in PUBLIC_SLOTS
        assert "axiom.turn:after_step" not in (dest / "main.py").read_text(encoding="utf-8")
        assert validate_mod_static(dest).passed

    bad = scaffold_mod("author.bad", target_dir=tmp_path / "bad")
    main = bad / "main.py"
    main.write_text(main.read_text(encoding="utf-8").replace("axiom.step:after_step", "axiom.turn:after_step"),
                    encoding="utf-8")
    res = test_mod(bad)
    assert not res.passed
    assert any("Unknown hook 'axiom.turn:after_step'" in e for e in res.errors)


def test_pyside6_import_is_forbidden_without_ui_dependency(tmp_path):
    dest = scaffold_mod("author.qtleak", target_dir=tmp_path / "q")
    main = dest / "main.py"
    main.write_text("from PySide6.QtWidgets import QWidget\n" + main.read_text(encoding="utf-8"), encoding="utf-8")
    res = validate_mod_static(dest)
    assert any("Forbidden UI dependency violation" in e for e in res.errors)

    # a dependency whose id merely contains "ui" does not allow it any more
    toml = dest / "mod.toml"
    toml.write_text(toml.read_text(encoding="utf-8") + '\n[dependencies]\n"author.guild" = "*"\n', encoding="utf-8")
    assert any("Forbidden UI" in e for e in validate_mod_static(dest).errors)


def test_tester_pythonpath_uses_os_pathsep():
    import inspect
    from axiom.kernel import tester
    src = inspect.getsource(tester._test_mod_directory)
    assert "os.pathsep" in src
    assert 'f"{project_root}:{' not in src
