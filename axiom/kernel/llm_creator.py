"""axiom/kernel/llm_creator.py

Headless LLM-driven mod creation and modification engine.
Orchestrates prompt assembling, LLM invocation, sandboxed staging (~/.cache/AxiomAI/staged_mods/),
unified diff computation, and automated testing before explicit user confirmation (Rule §12 & D14).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import difflib
import json
import os
from pathlib import Path
import shutil
from typing import Any

from axiom.backends.base import LLMBackend, LLMMessage
from axiom.config import AppConfig, build_llm_from_config, load_config, resolve_extraction_model
from axiom.kernel.manifest import ModManifest, load_manifest
from axiom.kernel.tester import ModTestResult, test_mod
from axiom.logger import logger


_SYSTEM_PROMPT_TEMPLATE = """You are Axiom AI's Mod Architect. You generate complete, fully functional mods for Axiom AI.
Axiom AI is an extensible, headless roleplaying and simulation engine.

### Formal Specification for mod.toml:
```toml
[mod]
id = "<author>.<name>"         # Strictly namespaced (e.g. 'community.hunger')
version = "0.1.0"               # Valid SemVer
axiom_api = 1                   # Integer, currently 1
name = "<Human Name>"
description = "<Description>"
author = "<Author Name>"

[contributes]
hooks = ["axiom.turn:after_step"] # Event hooks
slots = ["axiom.turn:prompt_sections"] # Slot contributions

[provides_slots]                # Optional custom slots declared by this mod
"<mod_id>:<slot_name>" = "collect" # Rule: 'collect' or 'first_win'

[dependencies]                  # Optional dependencies
# "axiom.ui.web" = ">=1.0.0"
```

### Public ModContext API (init(ctx: ModContext)):
- `ctx.mod_id`: The ID of this mod.
- `ctx.register_hook(hook_name: str, callback: Callable[[dict[str, Any]], Any]) -> None`
- `ctx.contribute_slot(slot_name: str, contribution: Any) -> None`
- `ctx.declare_slot(slot_name: str, rule: SlotRule = SlotRule.COLLECT) -> None`
- `ctx.register_service(service_name: str, service: Any) -> None`
- `ctx.get_service(service_name: str) -> Any | None`
- `ctx.patch(target: str, patch_type: PatchType, handler: Callable, priority: int = 100) -> None`

### Standard Official Hooks & Slots:
- Hooks:
  - `axiom.turn:gather_context`: Fired before LLM narrative prompt assembly.
  - `axiom.turn:execute_step`: Core turn step execution.
  - `axiom.turn:after_step`: Fired after rules and state mutations are applied.
  - `axiom.time:tick`: Fired when in-game time advances.
- Slots:
  - `axiom.turn:prompt_sections`: List of sections contributed to turn prompt (dict with id, title, content).
  - `axiom.turn:output_fields`: Dict/list of JSON fields requested from LLM output.
  - `axiom.world:rules`: Game rules contributed to arbitration engine.
  - `axiom.providers:drivers`: LLM drivers registered to provider manager.

### Reference Examples:
Example 1 (core.stat_dynamics):
```python
# main.py
from axiom.kernel.context import ModContext

def on_after_step(data: dict) -> None:
    # Perform decay or step cleanup
    pass

def init(ctx: ModContext) -> None:
    ctx.register_hook("axiom.turn:after_step", on_after_step)
```

Example 2 (hunger system):
```python
# main.py
from axiom.kernel.context import ModContext

def on_after_step(data: dict) -> None:
    # Update hunger state
    pass

def init(ctx: ModContext) -> None:
    ctx.contribute_slot("axiom.turn:prompt_sections", {
        "id": "hunger_gauge",
        "title": "Hunger",
        "content": "Status: Monitor player hunger level (0-100)."
    })
    ctx.contribute_slot("axiom.turn:output_fields", {
        "name": "hunger_delta",
        "type": "integer",
        "description": "Change in player hunger during this turn."
    })
    ctx.register_hook("axiom.turn:after_step", on_after_step)
```

### Output Format Requirement:
You MUST respond with a single valid JSON object containing:
{
  "mod_id": "<author>.<name>",
  "files": {
    "mod.toml": "<content of mod.toml>",
    "main.py": "<content of main.py>",
    "tests/test_<name>.py": "<content of unit test>"
  }
}
Do NOT wrap the JSON in commentary or extra text outside the JSON.
"""


@dataclass
class ModGenerationResult:
    """Structured report returned by the mod generation engine (Rule §12 & D14)."""

    mod_id: str
    staged_dir: Path
    manifest: ModManifest
    file_diffs: dict[str, str]
    tests_passed: bool
    error_report: str | None = None


def get_default_staged_mods_dir() -> Path:
    """Return the default root directory for sandboxed mod staging."""
    env_dir = os.environ.get("AXIOM_STAGED_MODS_DIR")
    if env_dir:
        return Path(env_dir).resolve()
    return (Path.home() / ".cache" / "AxiomAI" / "staged_mods").resolve()


def _parse_llm_json(raw_text: str) -> dict[str, Any]:
    """Parse JSON payload from LLM response, stripping markdown wrappers if present."""
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = text[first_brace : last_brace + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    return json.loads(text)


def _compute_file_diff(
    rel_path: str,
    new_content: str,
    existing_mod_dir: Path | None,
) -> str:
    """Generate a readable unified diff for a generated file."""
    new_lines = new_content.splitlines(keepends=True)
    if not new_lines or not new_lines[-1].endswith("\n"):
        new_lines = [line + ("\n" if not line.endswith("\n") else "") for line in new_lines]

    old_file = (existing_mod_dir / rel_path) if existing_mod_dir else None
    if old_file and old_file.is_file():
        old_lines = old_file.read_text(encoding="utf-8").splitlines(keepends=True)
        from_file = f"a/{rel_path}"
    else:
        old_lines = []
        from_file = "/dev/null"

    to_file = f"b/{rel_path}"
    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=from_file,
            tofile=to_file,
        )
    )
    return "".join(diff_lines) if diff_lines else f"--- {from_file}\n+++ {to_file}\n@@ (identical) @@\n"


def generate_mod(
    prompt: str,
    llm_backend: LLMBackend | None = None,
    staged_mods_base_dir: Path | str | None = None,
    target_mods_dir: Path | str = "mods",
    system_prompt: str | None = None,
) -> ModGenerationResult:
    """Generate or update a mod from natural language instruction in a staging sandbox.

    Args:
        prompt: Natural language user instruction.
        llm_backend: Optional pre-configured LLM backend (for testing or overrides).
        staged_mods_base_dir: Optional custom staging root folder.
        target_mods_dir: Base directory for installed mods (to compute diffs against).
        system_prompt: Optional override for system prompt.

    Returns:
        ModGenerationResult containing the diff, staging path, manifest, and test status.
    """
    if llm_backend is None:
        cfg = load_config()
        model = resolve_extraction_model(cfg)
        llm_backend = build_llm_from_config(cfg, model_override=model)

    sys_content = system_prompt or _SYSTEM_PROMPT_TEMPLATE
    messages: list[LLMMessage] = [
        {"role": "system", "content": sys_content},
        {"role": "user", "content": f"Generate an Axiom AI mod for this specification:\n{prompt}"},
    ]

    resp = llm_backend.complete(messages, temperature=0.2)
    raw_content = resp.content or resp.narrative_text or ""

    try:
        data = _parse_llm_json(raw_content)
    except Exception as err:
        raise ValueError(f"LLM returned invalid or unparseable JSON: {err}\nRaw output:\n{raw_content}") from err

    mod_id = data.get("mod_id")
    if not isinstance(mod_id, str) or "." not in mod_id:
        raise ValueError(f"LLM produced invalid mod_id '{mod_id}'. Must be namespaced like 'author.name'.")

    files = data.get("files")
    if not isinstance(files, dict) or "mod.toml" not in files:
        raise ValueError("LLM payload missing 'files' dictionary or required 'mod.toml'.")

    # Setup staging sandbox
    base_staged = Path(staged_mods_base_dir).resolve() if staged_mods_base_dir else get_default_staged_mods_dir()
    staged_dir = base_staged / mod_id
    if staged_dir.exists():
        shutil.rmtree(staged_dir)
    staged_dir.mkdir(parents=True, exist_ok=True)

    # Write files to staging
    for rel_path, content in files.items():
        file_path = staged_dir / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    # Load and validate manifest
    manifest = load_manifest(staged_dir)

    # Compute diff against installed mod if present
    existing_mod_path = Path(target_mods_dir).resolve() / mod_id
    existing_dir = existing_mod_path if existing_mod_path.is_dir() else None

    file_diffs: dict[str, str] = {}
    for rel_path, content in files.items():
        file_diffs[rel_path] = _compute_file_diff(rel_path, content, existing_dir)

    # Run automated test & validation in staging sandbox
    test_result: ModTestResult = test_mod(staged_dir)
    tests_passed = test_result.passed
    error_report = "\n".join(test_result.errors) if not tests_passed else None

    return ModGenerationResult(
        mod_id=mod_id,
        staged_dir=staged_dir,
        manifest=manifest,
        file_diffs=file_diffs,
        tests_passed=tests_passed,
        error_report=error_report,
    )


def apply_generated_mod(
    staged_dir: Path | str,
    target_mods_dir: Path | str = "mods",
    compile_axmod: bool = True,
    enable_in_config: bool = True,
) -> tuple[Path, Path | None]:
    """Apply and activate a staged mod after user confirmation (Rule §12 & D14).

    Copies files from staging sandbox to the target mod directory, optionally
    compiles a .axmod archive, and enables the mod in AppConfig.

    Returns:
        (installed_dir, axmod_path)
    """
    src_dir = Path(staged_dir).resolve()
    if not src_dir.is_dir() or not (src_dir / "mod.toml").is_file():
        raise FileNotFoundError(f"Invalid staged mod directory (missing mod.toml): {src_dir}")

    manifest = load_manifest(src_dir)

    dest_dir = (Path(target_mods_dir).resolve() / manifest.id)
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Copy files
    for src_file in src_dir.rglob("*"):
        if not src_file.is_file():
            continue
        rel = src_file.relative_to(src_dir)
        dest_file = dest_dir / rel
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dest_file)

    axmod_path: Path | None = None
    if compile_axmod:
        from axiom.cli.mods_cmd import pack_mod
        axmod_path = pack_mod(dest_dir)

    if enable_in_config:
        cfg = load_config()
        from axiom.config import save_config
        cfg.mod_settings.setdefault(manifest.id, {})["enabled"] = True
        save_config(cfg)

    logger.info("Applied generated mod '%s' to %s (axmod: %s)", manifest.id, dest_dir, axmod_path)
    return dest_dir, axmod_path
