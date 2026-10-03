"""axiom/kernel/llm_creator.py

Headless LLM-driven mod creation and modification engine.
Orchestrates prompt assembling, LLM invocation, writing into a preparation folder
(dossier de préparation, ~/.cache/AxiomAI/staged_mods/ by default — a plain folder
with no isolation), unified diff computation and a STATIC validation (Rule §12 & D14).

Nothing generated is executed before the user confirms: `generate_mod` only writes
files into the preparation folder, computes the diff and validates statically
(manifest, AST, known hook/slot names). The mod's code and tests run in
`apply_generated_mod`, i.e. after the user's "yes", before anything is installed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import difflib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from typing import Any

from axiom.backends.base import LLMBackend, LLMMessage
from axiom.config import AppConfig, load_config, resolve_extraction_model
from axiom.kernel.api import KERNEL_API, PUBLIC_HOOKS, PUBLIC_SLOTS
from axiom.kernel.manifest import _MOD_ID_REGEX, ModManifest, load_manifest
from axiom.kernel.tester import ModTestResult, test_mod, validate_mod_static
from axiom.logger import logger


class ModTestsFailedError(RuntimeError):
    """Raised by apply_generated_mod when the mod's tests fail (nothing is installed)."""


def _catalogue_text() -> str:
    hooks = "\n".join(f"  - `{name}`: {doc}" for name, doc in PUBLIC_HOOKS.items())
    slots = "\n".join(f"  - `{name}` ({rule}): {doc}" for name, (rule, doc) in PUBLIC_SLOTS.items())
    return f"- Hooks (the ONLY ones fired by Axiom):\n{hooks}\n- Slots (the ONLY ones read by Axiom):\n{slots}"


_SYSTEM_PROMPT_TEMPLATE = """You are Axiom AI's Mod Architect. You generate complete, fully functional mods for Axiom AI.
Axiom AI is an extensible, headless roleplaying and simulation engine.

### Formal Specification for mod.toml:
```toml
[mod]
id = "<author>.<name>"         # Strictly namespaced (e.g. 'community.hunger')
version = "0.1.0"               # Valid SemVer
axiom_api = __KERNEL_API__                   # Integer, must be __KERNEL_API__
name = "<Human Name>"
description = "<Description>"
author = "<Author Name>"

[contributes]
hooks = ["axiom.step:after_step"] # Hooks used (only names from the list below)
slots = ["axiom.turn:prompt_sections"] # Slots contributed to (only names from the list below)

[provides_slots]                # Optional custom slots declared by this mod
"<mod_id>:<slot_name>" = "collect" # Rule: 'collect', 'chain' or 'exclusive'

[dependencies]                  # Optional dependencies
# "axiom.turn" = ">=1.0.0"

[storage]                       # Save data of the mod (rewound/forked by Axiom, no code needed)
# hunger = { policy = "versioned_kv" }   # read/written with ctx.store
```

### Public ModContext API (init(ctx: ModContext)):
- `ctx.mod_id`: The ID of this mod.
- `ctx.register_hook(hook_name: str, callback: Callable[[Any], Any]) -> None`
- `ctx.contribute_slot(slot_name: str, contribution: Any) -> None`
- `ctx.declare_slot(slot_name: str, rule: SlotRule = SlotRule.COLLECT) -> None`
- `ctx.register_service(service_name: str, service: Any) -> None`
- `ctx.get_service(service_name: str) -> Any | None`
- `ctx.get_slot(slot_name: str) -> Any`, `ctx.invoke_hook(hook_name: str, *args) -> list`
- `ctx.spawn_job(target: Callable, *args) -> Thread` (stop when `ctx.should_stop()`)
- `ctx.patch(target: str, patch_type: PatchType, handler: Callable, priority: int = 100) -> None`
  (target 'module:function' or 'module:Class.method'; an unknown target is an error)
- `ctx.store.get(turn_ctx, key, default)` / `ctx.store.set(turn_ctx, key, value)` /
  `ctx.store.delete(turn_ctx, key)`: save data of this mod (JSON values), written with the
  turn and rewound/forked with the save. Declare it in `[storage]` as `versioned_kv`.

### Official Hooks & Slots (any other `axiom.*` name is refused: it would never be called):
__CATALOGUE__

Hook callbacks receive the turn context object (attributes such as `save_id`, `turn_id`,
`user_input`, `elapsed_minutes`, `write_batch`).

### Reference Examples:
Example 1 (after-step hook):
```python
# main.py
from typing import Any
from axiom.kernel.context import ModContext

def on_after_step(turn_ctx: Any) -> None:
    # Perform decay or step cleanup
    pass

def init(ctx: ModContext) -> None:
    ctx.register_hook("axiom.step:after_step", on_after_step)
```

Example 2 (hunger gauge that drops with time; mod.toml declares
`[storage] hunger = { policy = "versioned_kv" }`):
```python
# main.py
from typing import Any
from axiom.kernel.context import ModContext

def init(ctx: ModContext) -> None:
    def hunger_section(turn_ctx: Any):
        hunger = ctx.store.get(turn_ctx, "hunger", 100)
        return ("system", 0, f"The player's hunger is {hunger}/100 (0 = starving).")

    def on_hunger_delta(value: Any, turn_ctx: Any) -> None:
        # Parsed value of the 'hunger_delta' field of the LLM output (eating, etc.)
        hunger = ctx.store.get(turn_ctx, "hunger", 100)
        ctx.store.set(turn_ctx, "hunger", max(0, min(100, hunger + int(value))))

    def on_after_step(turn_ctx: Any) -> None:
        # Time passes: -1 hunger per 30 in-game minutes
        hunger = ctx.store.get(turn_ctx, "hunger", 100)
        drop = int(getattr(turn_ctx, "elapsed_minutes", 0) or 0) // 30
        ctx.store.set(turn_ctx, "hunger", max(0, hunger - drop))

    ctx.contribute_slot("axiom.turn:prompt_sections", hunger_section)
    ctx.contribute_slot("axiom.turn:output_fields", {
        "name": "hunger_delta",
        "schema": 0,
        "instruction": "When the player eats or starves, report the hunger change (+/- integer).",
        "handler": on_hunger_delta,
    })
    ctx.register_hook("axiom.step:after_step", on_after_step)
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


def build_system_prompt() -> str:
    """System prompt of the creator, built from the single public catalogue."""
    return (
        _SYSTEM_PROMPT_TEMPLATE.replace("__KERNEL_API__", str(KERNEL_API))
        .replace("__CATALOGUE__", _catalogue_text())
    )


@dataclass
class ModGenerationResult:
    """Structured report returned by the mod generation engine (Rule §12 & D14)."""

    mod_id: str
    staged_dir: Path
    manifest: ModManifest
    file_diffs: dict[str, str]
    # Static validation only (manifest, AST, hook/slot names): no generated code was run.
    validation_passed: bool
    error_report: str | None = None

    @property
    def tests_passed(self) -> bool:
        """Backward-compatible alias of `validation_passed` (static validation, nothing executed)."""
        return self.validation_passed


def get_default_staged_mods_dir() -> Path:
    """Return the default root of the preparation folders (one per generated mod)."""
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


def _safe_relative_path(rel_path: Any) -> PurePosixPath:
    """Validate a file path proposed by the LLM: relative, inside the preparation folder."""
    if not isinstance(rel_path, str) or not rel_path.strip():
        raise ValueError(f"Invalid file path in LLM payload: {rel_path!r}")
    norm = rel_path.replace("\\", "/")
    pure = PurePosixPath(norm)
    if pure.is_absolute() or norm.startswith("/") or (len(norm) > 1 and norm[1] == ":"):
        raise ValueError(f"Refused absolute file path from LLM: '{rel_path}'")
    if any(part in ("..", "") for part in norm.split("/")):
        raise ValueError(f"Refused file path leaving the preparation folder: '{rel_path}'")
    return pure


def generate_mod(
    prompt: str,
    llm_backend: LLMBackend | None = None,
    staged_mods_base_dir: Path | str | None = None,
    target_mods_dir: Path | str | None = None,
    system_prompt: str | None = None,
) -> ModGenerationResult:
    """Generate or update a mod from a natural language instruction, into a preparation folder.

    Nothing generated is executed here: the result carries the diff and a static
    validation only. Tests run in `apply_generated_mod`, after confirmation.

    Args:
        prompt: Natural language user instruction.
        llm_backend: Optional pre-configured LLM backend (for testing or overrides).
        staged_mods_base_dir: Optional custom root of the preparation folders.
        target_mods_dir: Installed mods folder to diff against (default: user mods folder).
        system_prompt: Optional override for system prompt.

    Raises:
        ValueError: invalid LLM payload, or a file path leaving the preparation folder
            (nothing is written in that case).
    """
    if llm_backend is None:
        cfg = load_config()
        model = resolve_extraction_model(cfg)
        from axiom.session import resolve_llm_backend  # axiom.providers only (M8)
        llm_backend = resolve_llm_backend(cfg, model_override=model)

    sys_content = system_prompt or build_system_prompt()
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
    if not isinstance(mod_id, str) or not _MOD_ID_REGEX.match(mod_id) or ".." in mod_id:
        raise ValueError(f"LLM produced invalid mod_id '{mod_id}'. Must be namespaced like 'author.name'.")

    files = data.get("files")
    if not isinstance(files, dict) or "mod.toml" not in files:
        raise ValueError("LLM payload missing 'files' dictionary or required 'mod.toml'.")

    # Validate every path BEFORE writing anything.
    safe_files: dict[str, str] = {}
    for rel_path, content in files.items():
        pure = _safe_relative_path(rel_path)
        if not isinstance(content, str):
            raise ValueError(f"Content of '{rel_path}' must be a string.")
        safe_files[pure.as_posix()] = content

    base_staged = Path(staged_mods_base_dir).resolve() if staged_mods_base_dir else get_default_staged_mods_dir()
    staged_dir = (base_staged / mod_id).resolve()
    if base_staged not in staged_dir.parents:
        raise ValueError(f"Refused preparation folder outside {base_staged}: {staged_dir}")
    if staged_dir.exists():
        shutil.rmtree(staged_dir)
    staged_dir.mkdir(parents=True, exist_ok=True)

    for rel_path, content in safe_files.items():
        file_path = (staged_dir / rel_path).resolve()
        if staged_dir not in file_path.parents:
            shutil.rmtree(staged_dir, ignore_errors=True)
            raise ValueError(f"Refused file path leaving the preparation folder: '{rel_path}'")
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    # Static validation only: nothing of the generated code is executed (§12).
    validation: ModTestResult = validate_mod_static(staged_dir)
    if validation.manifest is None:
        raise ValueError("Generated manifest is invalid: " + "; ".join(validation.errors))
    manifest = validation.manifest
    errors = list(validation.errors)
    if manifest.id != mod_id:
        errors.append(f"mod_id '{mod_id}' does not match the manifest id '{manifest.id}'.")

    # Compute diff against installed mod if present
    installed_root = _resolve_target_mods_dir(target_mods_dir)
    existing_mod_path = installed_root / manifest.id
    existing_dir = existing_mod_path if existing_mod_path.is_dir() else None

    file_diffs: dict[str, str] = {}
    for rel_path, content in safe_files.items():
        file_diffs[rel_path] = _compute_file_diff(rel_path, content, existing_dir)
    if existing_dir is not None:
        for old_file in sorted(existing_dir.rglob("*")):
            rel = old_file.relative_to(existing_dir).as_posix()
            if old_file.is_file() and rel not in safe_files and "__pycache__" not in rel:
                file_diffs[rel] = f"--- a/{rel}\n+++ /dev/null\n@@ file removed @@\n"

    return ModGenerationResult(
        mod_id=mod_id,
        staged_dir=staged_dir,
        manifest=manifest,
        file_diffs=file_diffs,
        validation_passed=not errors,
        error_report="\n".join(errors) if errors else None,
    )


def _resolve_target_mods_dir(target_mods_dir: Path | str | None) -> Path:
    if target_mods_dir is None:
        from axiom.kernel.loader import get_user_mods_dir
        return get_user_mods_dir()
    return Path(target_mods_dir).resolve()


def apply_generated_mod(
    staged_dir: Path | str,
    target_mods_dir: Path | str | None = None,
    compile_axmod: bool = True,
    enable_in_config: bool = True,
    run_tests: bool = True,
) -> tuple[Path, Path | None]:
    """Install a prepared mod after the user's confirmation (Rule §12 & D14).

    Order: static validation, then the mod's tests (`test_mod`, which executes its code:
    this is the first execution, after confirmation), then a clean replacement of the
    installed folder (old files do not survive), optional .axmod next to the
    preparation folder, and activation in the config.

    Raises:
        ModTestsFailedError: validation or tests failed; nothing is installed.

    Returns:
        (installed_dir, axmod_path)
    """
    src_dir = Path(staged_dir).resolve()
    if not src_dir.is_dir() or not (src_dir / "mod.toml").is_file():
        raise FileNotFoundError(f"Invalid preparation folder (missing mod.toml): {src_dir}")

    if run_tests:
        result = test_mod(src_dir)
        if not result.passed:
            report = "\n".join(f"  - {e}" for e in result.errors)
            if result.pytest_output:
                report += "\n" + result.pytest_output.strip()
            raise ModTestsFailedError(report)
        manifest = result.manifest
    else:
        static = validate_mod_static(src_dir)
        if static.manifest is None:
            raise ModTestsFailedError("\n".join(static.errors))
        manifest = static.manifest

    target_root = _resolve_target_mods_dir(target_mods_dir)
    target_root.mkdir(parents=True, exist_ok=True)
    dest_dir = target_root / manifest.id

    # Clean replacement: copy into a temporary sibling, then swap.
    tmp_dir = Path(tempfile.mkdtemp(prefix=f".{manifest.id}.", dir=target_root))
    try:
        shutil.copytree(
            src_dir,
            tmp_dir / "mod",
            ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"),
        )
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        (tmp_dir / "mod").rename(dest_dir)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    axmod_path: Path | None = None
    if compile_axmod:
        from axiom.cli.mods_cmd import pack_mod
        # Next to the preparation folder, never in the repository nor in a discovered folder.
        axmod_path = pack_mod(dest_dir, output_path=src_dir.parent / f"{manifest.id}-{manifest.version}.axmod")

    if enable_in_config:
        cfg = load_config()
        from axiom.config import save_config
        cfg.mod_settings.setdefault(manifest.id, {})["enabled"] = True
        save_config(cfg)

    logger.info("Applied generated mod '%s' to %s (axmod: %s)", manifest.id, dest_dir, axmod_path)
    return dest_dir, axmod_path
