"""tests/test_mod_creator.py

Comprehensive test suite for Phase 4:
- Scaffolding engine (scaffold_mod / axiom mod new)
- Mod tester and validator (test_mod / axiom mod test)
- Hot reload dev watcher (poll_mod_once / axiom mod dev)
- LLM mod creator and staging sandbox (generate_mod / apply_generated_mod)
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any
import pytest

from axiom.backends.base import LLMBackend, LLMMessage, LLMResponse
from axiom.cli.main import main as cli_main
from axiom.cli.mods_cmd import pack_mod
from axiom.kernel.context import ModContext
from axiom.kernel.dev import poll_mod_once
from axiom.kernel.llm_creator import (
    ModGenerationResult,
    apply_generated_mod,
    generate_mod,
)
from axiom.kernel.manifest import parse_manifest_file
from axiom.kernel.registry import KernelRegistry
from axiom.kernel.scaffold import scaffold_mod
from axiom.kernel.tester import ModTestResult, test_mod


class MockLLMBackend(LLMBackend):
    """Deterministic mock LLM for testing mod generation."""

    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.captured_messages: list[LLMMessage] = []

    def is_available(self) -> bool:
        return True

    def complete(
        self,
        messages: list[LLMMessage],
        stream: bool = False,
        temperature: float = 0.7,
        top_p: float = 1.0,
        response_format: str | None = None,
        stop_sequences: list[str] | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self.captured_messages = list(messages)
        return LLMResponse(content=self.response_text, finish_reason="stop")

    def stream_tokens(self, messages, **kwargs):
        yield self.response_text


# ---------------------------------------------------------------------------
# 1. Scaffolding Tests
# ---------------------------------------------------------------------------


def test_scaffold_mod_hook_archetype(tmp_path: Path) -> None:
    """Verify scaffolding a 'hook' type mod produces standard directory and valid files."""
    dest = tmp_path / "community.weather"
    created = scaffold_mod("community.weather", mod_type="hook", target_dir=dest)

    assert created == dest
    assert (dest / "mod.toml").is_file()
    assert (dest / "main.py").is_file()
    assert (dest / "tests" / "test_weather.py").is_file()
    assert (dest / "locales" / "en.json").is_file()

    # Validate manifest
    manifest = parse_manifest_file(dest / "mod.toml")
    assert manifest.id == "community.weather"
    assert manifest.axiom_api == 1
    assert "axiom.turn:after_step" in manifest.contributes.hooks

    # Validate test runner
    result = test_mod(dest)
    assert result.passed, f"Scaffolded mod failed test_mod: {result.errors}"


def test_scaffold_mod_slot_archetype(tmp_path: Path) -> None:
    """Verify scaffolding a 'slot' archetype declares slots and contributes."""
    dest = tmp_path / "community.reputation"
    scaffold_mod("community.reputation", mod_type="slot", target_dir=dest)

    manifest = parse_manifest_file(dest / "mod.toml")
    assert "community.reputation:features" in manifest.provides_slots
    assert "axiom.turn:prompt_sections" in manifest.contributes.slots
    assert "axiom.turn:output_fields" in manifest.contributes.slots

    result = test_mod(dest)
    assert result.passed, f"Slot mod failed test_mod: {result.errors}"


def test_scaffold_mod_data_archetype(tmp_path: Path) -> None:
    """Verify scaffolding a 'data' archetype declares storage tables."""
    dest = tmp_path / "community.quest_log"
    scaffold_mod("community.quest_log", mod_type="data", target_dir=dest)

    manifest = parse_manifest_file(dest / "mod.toml")
    assert "quest_log_records" in manifest.storage.get("tables", [])

    result = test_mod(dest)
    assert result.passed, f"Data mod failed test_mod: {result.errors}"


def test_scaffold_mod_validation_errors(tmp_path: Path) -> None:
    """Verify unnamespaced mod IDs and invalid types are rejected."""
    with pytest.raises(ValueError, match="namespaced"):
        scaffold_mod("unnamespaced_mod", target_dir=tmp_path / "invalid")

    with pytest.raises(ValueError, match="Invalid mod_type"):
        scaffold_mod("author.valid", mod_type="unknown_type", target_dir=tmp_path / "invalid2")

    # Target directory already having a mod.toml raises FileExistsError
    dest = tmp_path / "existing"
    scaffold_mod("author.existing", target_dir=dest)
    with pytest.raises(FileExistsError):
        scaffold_mod("author.existing", target_dir=dest)


# ---------------------------------------------------------------------------
# 2. Mod Tester & Validator Tests
# ---------------------------------------------------------------------------


def test_mod_tester_on_valid_and_broken_manifest(tmp_path: Path) -> None:
    """Verify test_mod reports manifest errors."""
    dest = tmp_path / "test.broken"
    dest.mkdir(parents=True)
    # Missing mod.toml
    res = test_mod(dest)
    assert not res.passed
    assert any("Manifest error" in e for e in res.errors)

    # Malformed mod.toml
    (dest / "mod.toml").write_text("invalid = [toml content", encoding="utf-8")
    res = test_mod(dest)
    assert not res.passed


def test_mod_tester_forbidden_ui_import_rule_d4(tmp_path: Path) -> None:
    """Rule D4: Mod importing PyQt6/ui without declaring UI dependency must fail."""
    dest = tmp_path / "community.illegal_ui"
    scaffold_mod("community.illegal_ui", target_dir=dest)

    # Inject forbidden UI import into main.py
    main_py = dest / "main.py"
    content = main_py.read_text(encoding="utf-8")
    content = "import PyQt6.QtWidgets\n" + content
    main_py.write_text(content, encoding="utf-8")

    res = test_mod(dest)
    assert not res.passed
    assert any("Forbidden UI dependency violation" in e for e in res.errors)


def test_mod_tester_allowed_ui_import_when_declared(tmp_path: Path) -> None:
    """When UI dependency is explicitly declared in mod.toml, UI import is permitted."""
    dest = tmp_path / "community.legal_ui"
    scaffold_mod("community.legal_ui", target_dir=dest)

    # Add dependency to mod.toml
    mod_toml = dest / "mod.toml"
    content = mod_toml.read_text(encoding="utf-8")
    content += "\n[dependencies]\n\"axiom.ui.web\" = \"*\"\n"
    mod_toml.write_text(content, encoding="utf-8")

    main_py = dest / "main.py"
    main_py.write_text("from main_web import WEB_DIR\n\ndef init(ctx):\n    pass\n", encoding="utf-8")

    res = test_mod(dest)
    # UI import violation should NOT be raised
    assert not any("Forbidden UI dependency violation" in e for e in res.errors)


def test_mod_tester_with_failing_unit_test(tmp_path: Path) -> None:
    """Verify that failing unit tests inside tests/ folder cause test_mod to fail."""
    dest = tmp_path / "community.failing_test"
    scaffold_mod("community.failing_test", target_dir=dest)

    # Make test fail
    test_file = dest / "tests" / "test_failing_test.py"
    test_file.write_text("def test_will_fail():\n    assert False, 'Deliberate failure'\n", encoding="utf-8")

    res = test_mod(dest)
    assert not res.passed
    assert any("failed with return code" in e for e in res.errors)


def test_mod_tester_on_axmod_archive(tmp_path: Path) -> None:
    """Verify test_mod functions identically on packaged .axmod archives."""
    dest = tmp_path / "community.archived"
    scaffold_mod("community.archived", target_dir=dest)

    # Pack to .axmod
    archive_path = pack_mod(dest, output_path=tmp_path / "archived.axmod")
    assert archive_path.is_file()

    res = test_mod(archive_path)
    assert res.passed, f"Testing .axmod archive failed: {res.errors}"


# ---------------------------------------------------------------------------
# 3. Hot Reload Dev Watcher Tests
# ---------------------------------------------------------------------------


def test_mod_dev_poll_and_cleanup(tmp_path: Path) -> None:
    """Verify poll_mod_once detects changes, calls cleanup(), and updates registry."""
    dest = tmp_path / "community.hotreload"
    scaffold_mod("community.hotreload", target_dir=dest)

    registry = KernelRegistry()
    mtime, reloaded, ctx = poll_mod_once(dest, 0.0, None, registry)
    assert reloaded
    assert ctx is not None
    assert ctx.mod_id == "community.hotreload"
    assert any(mid == "community.hotreload" for mid, _ in registry._hooks.get("axiom.turn:after_step", []))

    # Second poll without changes should do nothing

    mtime2, reloaded2, ctx2 = poll_mod_once(dest, mtime, ctx, registry)
    assert not reloaded2
    assert ctx2 is ctx

    # Now modify main.py with artificial delay to ensure mtime advances
    time.sleep(0.05)
    main_py = dest / "main.py"
    main_py.write_text(
        main_py.read_text(encoding="utf-8") + "\n# Extra comment triggering reload\n",
        encoding="utf-8",
    )

    mtime3, reloaded3, ctx3 = poll_mod_once(dest, mtime, ctx, registry)
    assert reloaded3
    assert mtime3 > mtime
    assert ctx3 is not ctx  # New context instantiated


# ---------------------------------------------------------------------------
# 4. LLM Creator & Staging Tests
# ---------------------------------------------------------------------------


def test_llm_mod_generation_and_staging_lifecycle(tmp_path: Path) -> None:
    """Test full generation lifecycle: prompt -> staging -> diff -> confirmation -> apply."""
    mock_payload = {
        "mod_id": "community.fatigue",
        "files": {
            "mod.toml": """[mod]
id = "community.fatigue"
version = "0.1.0"
axiom_api = 1
name = "Fatigue System"
description = "Tracks physical exhaustion"
author = "LLM Creator"

[contributes]
hooks = ["axiom.turn:after_step"]
slots = ["axiom.turn:prompt_sections"]
""",
            "main.py": """from axiom.kernel.context import ModContext

def on_after_step(data: dict) -> None:
    pass

def init(ctx: ModContext) -> None:
    ctx.register_hook("axiom.turn:after_step", on_after_step)
    ctx.contribute_slot("axiom.turn:prompt_sections", {
        "id": "fatigue_section",
        "title": "Fatigue",
        "content": "Fatigue: Moderate (40/100)",
    })
""",
            "tests/test_fatigue.py": """from axiom.kernel.manifest import parse_manifest_file
from pathlib import Path

def test_fatigue_manifest():
    manifest = parse_manifest_file(Path(__file__).parent.parent / "mod.toml")
    assert manifest.id == "community.fatigue"
""",
        },
    }

    mock_llm = MockLLMBackend(f"```json\n{json.dumps(mock_payload)}\n```")
    staged_root = tmp_path / "staged"
    installed_root = tmp_path / "installed"

    # Step 1: Generate into sandbox
    gen_result: ModGenerationResult = generate_mod(
        prompt="Create a fatigue system that tracks exhaustion",
        llm_backend=mock_llm,
        staged_mods_base_dir=staged_root,
        target_mods_dir=installed_root,
    )

    assert gen_result.mod_id == "community.fatigue"
    assert gen_result.staged_dir == staged_root / "community.fatigue"
    assert gen_result.staged_dir.is_dir()
    assert (gen_result.staged_dir / "mod.toml").is_file()
    assert gen_result.tests_passed, f"Staging tests failed: {gen_result.error_report}"

    # Diffs must be present for all 3 files
    assert "mod.toml" in gen_result.file_diffs
    assert "main.py" in gen_result.file_diffs
    assert "tests/test_fatigue.py" in gen_result.file_diffs

    # Strict contract: Nothing is written to installed_root yet!
    assert not (installed_root / "community.fatigue").exists()

    # Step 2: Apply upon explicit confirmation
    dest_path, axmod_path = apply_generated_mod(
        gen_result.staged_dir,
        target_mods_dir=installed_root,
        compile_axmod=True,
        enable_in_config=False,
    )

    assert dest_path == installed_root / "community.fatigue"
    assert (dest_path / "mod.toml").is_file()
    assert (dest_path / "main.py").is_file()
    assert axmod_path is not None and axmod_path.is_file()


# ---------------------------------------------------------------------------
# 5. CLI Subcommand Integration Tests
# ---------------------------------------------------------------------------


def test_cli_mod_new_and_test(tmp_path: Path, capsys) -> None:
    """Test `axiom mod new` and `axiom mod test` CLI commands."""
    mod_dir = tmp_path / "community.cli_sample"
    code = cli_main(["mod", "new", "community.cli_sample", "--dir", str(mod_dir), "--type", "hook"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Successfully scaffolded" in captured.out

    test_code = cli_main(["mod", "test", str(mod_dir)])
    assert test_code == 0
    captured_test = capsys.readouterr()
    assert "SUCCESS: Mod 'community.cli_sample'" in captured_test.out


def test_cli_mod_generate(tmp_path: Path, monkeypatch, capsys) -> None:
    """Test `axiom mod generate --yes` command with mocked backend."""
    mock_payload = {
        "mod_id": "community.test_gen",
        "files": {
            "mod.toml": """[mod]
id = "community.test_gen"
version = "0.1.0"
axiom_api = 1
name = "Test Gen"
""",
            "main.py": """def init(ctx): pass\n""",
        },
    }
    mock_llm = MockLLMBackend(json.dumps(mock_payload))
    monkeypatch.setattr("axiom.kernel.llm_creator.build_llm_from_config", lambda *a, **k: mock_llm)

    staged_dir = tmp_path / "staged"
    installed_dir = tmp_path / "installed"
    monkeypatch.setenv("AXIOM_STAGED_MODS_DIR", str(staged_dir))

    # Mock apply_generated_mod's default target_mods_dir to installed_dir
    orig_apply = apply_generated_mod
    monkeypatch.setattr(
        "axiom.kernel.llm_creator.apply_generated_mod",
        lambda staged, **k: orig_apply(staged, target_mods_dir=installed_dir, compile_axmod=False, enable_in_config=False),
    )

    code = cli_main(["mod", "generate", "Generate a test mod", "--yes"])
    assert code == 0
    captured = capsys.readouterr()
    assert "GENERATED MOD: community.test_gen" in captured.out
    assert "Diff for mod.toml" in captured.out
    assert (installed_dir / "community.test_gen" / "mod.toml").is_file()


def test_web_api_mod_endpoints(tmp_path: Path, monkeypatch) -> None:
    """Test Web API endpoints /api/mods (GET), /api/mods/generate (POST), and /api/mods/apply (POST)."""
    import io
    from main_web import AxiomWebHandler

    mock_payload = {
        "mod_id": "community.web_mod",
        "files": {
            "mod.toml": """[mod]
id = "community.web_mod"
version = "0.1.0"
axiom_api = 1
name = "Web Generated Mod"
""",
            "main.py": """def init(ctx): pass\n""",
        },
    }
    mock_llm = MockLLMBackend(json.dumps(mock_payload))
    monkeypatch.setattr("axiom.kernel.llm_creator.build_llm_from_config", lambda *a, **k: mock_llm)

    staged_dir = tmp_path / "staged_web"
    installed_dir = tmp_path / "installed_web"
    monkeypatch.setenv("AXIOM_STAGED_MODS_DIR", str(staged_dir))

    orig_apply = apply_generated_mod
    monkeypatch.setattr(
        "axiom.kernel.llm_creator.apply_generated_mod",
        lambda staged, **k: orig_apply(staged, target_mods_dir=installed_dir, compile_axmod=False, enable_in_config=False),
    )

    class DummyRequest:
        def makefile(self, *args, **kwargs):
            return io.BytesIO()

    # Create handler mock
    handler = AxiomWebHandler.__new__(AxiomWebHandler)
    handler.rfile = io.BytesIO()
    handler.wfile = io.BytesIO()
    handler.headers = {"Host": "127.0.0.1"}

    sent_data = []
    handler.send_json = lambda data, code=200: sent_data.append((code, data))
    handler.send_error_json = lambda code, msg: sent_data.append((code, msg))

    # 1. Test POST /api/mods/generate
    handler.handle_api_post("/api/mods/generate", {"prompt": "Create web mod"})
    assert len(sent_data) == 1
    code, resp = sent_data[0]
    assert code == 200
    assert resp["status"] == "success"
    assert resp["mod_id"] == "community.web_mod"
    assert "mod.toml" in resp["file_diffs"]
    staged_path = resp["staged_dir"]

    # 2. Test POST /api/mods/apply
    sent_data.clear()
    handler.handle_api_post("/api/mods/apply", {"staged_dir": staged_path})
    assert len(sent_data) == 1
    code2, resp2 = sent_data[0]
    assert code2 == 200
    assert resp2["status"] == "success"
    assert (installed_dir / "community.web_mod" / "mod.toml").is_file()

    # 3. Test GET /api/mods
    sent_data.clear()
    handler.handle_api_get("/api/mods", "")
    assert len(sent_data) == 1
    code3, resp3 = sent_data[0]
    assert code3 == 200
    assert isinstance(resp3, list)

