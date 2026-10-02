"""axiom/kernel/scaffold.py

Scaffolding generator for Axiom AI mods (`axiom mod new`).
Generates standard mod directory structure, manifest, entry point, tests, and locales.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from axiom.kernel.manifest import ManifestError, _MOD_ID_REGEX, parse_manifest_file
from axiom.logger import logger


_VALID_MOD_TYPES = {"hook", "slot", "data"}


def _generate_mod_toml(
    mod_id: str,
    mod_type: str,
    name: str,
    description: str,
    author: str,
) -> str:
    """Generate mod.toml content based on mod type."""
    name_part = mod_id.split(".")[-1]

    if mod_type == "slot":
        return f"""[mod]
id = "{mod_id}"
version = "0.1.0"
axiom_api = 1
name = "{name}"
description = "{description}"
author = "{author}"

[provides_slots]
"{mod_id}:features" = "collect"

[contributes]
slots = [
    "axiom.turn:prompt_sections",
    "axiom.turn:output_fields"
]
"""
    elif mod_type == "data":
        return f"""[mod]
id = "{mod_id}"
version = "0.1.0"
axiom_api = 1
name = "{name}"
description = "{description}"
author = "{author}"

[storage]
tables = [
    "{name_part}_records"
]

[contributes]
hooks = [
    "axiom.step:after_step"
]
"""
    else:  # default "hook"
        return f"""[mod]
id = "{mod_id}"
version = "0.1.0"
axiom_api = 1
name = "{name}"
description = "{description}"
author = "{author}"

[contributes]
hooks = [
    "axiom.step:gather_context",
    "axiom.step:after_step"
]
"""


def _generate_main_py(mod_id: str, mod_type: str, name: str) -> str:
    """Generate main.py template based on mod type."""
    name_part = mod_id.split(".")[-1]
    fn_part = re.sub(r"\W", "_", name_part)

    if mod_type == "slot":
        return f'''"""{mod_id} - Main mod entry point.

Provides and contributes to Axiom extension slots.
"""

from __future__ import annotations

from typing import Any

from axiom.kernel.context import ModContext
from axiom.kernel.registry import SlotRule
from axiom.logger import logger


def init(ctx: ModContext) -> None:
    """Initialize the mod, declare custom slots, and contribute to official slots."""
    logger.info("Initializing slot mod '%s'", ctx.mod_id)

    # 1. Declare slot provided by this mod
    ctx.declare_slot(f"{{ctx.mod_id}}:features", SlotRule.COLLECT)

    # 2. Contribute to official axiom.turn slots
    ctx.contribute_slot(
        "axiom.turn:prompt_sections",
        {{
            "position": "system",
            "text": "{name}: special conditions are active.",
            "depth": 50,
        }},
    )
    # Receives the parsed value of the '{name_part}_delta' field of the LLM output
    ctx.contribute_slot("axiom.turn:output_fields", ("{name_part}_delta", on_{fn_part}_delta))


def on_{fn_part}_delta(value: Any, turn_ctx: Any) -> None:
    """Handler for the '{name_part}_delta' output field."""
    logger.debug("[%s] {name_part}_delta = %s", turn_ctx, value)
'''
    elif mod_type == "data":
        return f'''"""{mod_id} - Main mod entry point.

Data storage and state management mod for Axiom AI.
"""

from __future__ import annotations

from typing import Any

from axiom.kernel.context import ModContext
from axiom.logger import logger


def on_after_step(turn_ctx: Any) -> None:
    """Hook invoked after the step's rules and mutations (receives the turn context)."""
    logger.debug("[{mod_id}] Recording step data")


def init(ctx: ModContext) -> None:
    """Initialize the data mod and register lifecycle hooks."""
    logger.info("Initializing data mod '%s'", ctx.mod_id)
    ctx.register_hook("axiom.step:after_step", on_after_step)
'''
    else:  # "hook"
        return f'''"""{mod_id} - Main mod entry point.

Standard hook-based mod for Axiom AI.
"""

from __future__ import annotations

from typing import Any

from axiom.kernel.context import ModContext
from axiom.logger import logger


def on_gather_context(turn_ctx: Any) -> None:
    """Hook invoked once the context is gathered, before the prompt is built."""
    logger.debug("[{mod_id}] Gathering context")


def on_after_step(turn_ctx: Any) -> None:
    """Hook invoked after the step's rules and narration have executed."""
    logger.debug("[{mod_id}] Step post-processing")


def init(ctx: ModContext) -> None:
    """Initialize the mod and register event hooks."""
    logger.info("Initializing hook mod '%s'", ctx.mod_id)
    ctx.register_hook("axiom.step:gather_context", on_gather_context)
    ctx.register_hook("axiom.step:after_step", on_after_step)
'''


def _generate_test_py(mod_id: str, mod_type: str) -> str:
    """Generate tests/test_<name>.py template."""
    return f'''"""Unit tests for {mod_id}."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from axiom.kernel.context import ModContext
from axiom.kernel.manifest import parse_manifest_file
from axiom.kernel.registry import KernelRegistry


def test_{mod_id.replace(".", "_")}_initialization() -> None:
    """Verify that {mod_id} initializes properly in an isolated ModContext."""
    mod_root = Path(__file__).resolve().parent.parent
    manifest = parse_manifest_file(mod_root / "mod.toml")

    assert manifest.id == "{mod_id}"
    assert manifest.axiom_api == 1

    registry = KernelRegistry()
    ctx = ModContext(manifest, registry)

    spec = importlib.util.spec_from_file_location("mod_main", mod_root / "main.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert hasattr(module, "init") and callable(module.init)
    module.init(ctx)

    # Clean up and ensure unregistration (Rule D11)
    ctx.cleanup()
'''


def scaffold_mod(
    mod_id: str,
    mod_type: str = "hook",
    target_dir: Path | str | None = None,
    author: str = "Axiom Community",
    description: str = "",
) -> Path:
    """Scaffold a new Axiom AI mod directory.

    Args:
        mod_id: Namespaced mod ID (e.g. 'author.my_mod').
        mod_type: Template type ('hook', 'slot', or 'data').
        target_dir: Target directory path. If None, defaults to `<user mods folder>/<mod_id>`
            (`axiom.paths.get_mods_dir()`), never the sources of the repository.
        author: Author name.
        description: Short human-readable description.

    Returns:
        Path of the generated mod root directory.

    Raises:
        ValueError: If mod_id does not conform to namespace regex or mod_type is invalid.
        FileExistsError: If target directory already contains a mod.toml.
    """
    mod_id = mod_id.strip()
    if not _MOD_ID_REGEX.match(mod_id):
        raise ValueError(
            f"Invalid mod_id '{mod_id}'. Mod ID must be namespaced like 'author.name' "
            f"(alphanumeric, underscores, hyphens, separated by dot)."
        )

    mod_type = mod_type.strip().lower()
    if mod_type not in _VALID_MOD_TYPES:
        raise ValueError(
            f"Invalid mod_type '{mod_type}'. Must be one of: {sorted(_VALID_MOD_TYPES)}"
        )

    if target_dir:
        dest_dir = Path(target_dir).resolve()
    else:
        from axiom.kernel.loader import get_user_mods_dir
        dest_dir = (get_user_mods_dir() / mod_id).resolve()

    manifest_file = dest_dir / "mod.toml"
    if manifest_file.exists():
        raise FileExistsError(f"Mod already exists at: {dest_dir} ({manifest_file})")

    dest_dir.mkdir(parents=True, exist_ok=True)
    tests_dir = dest_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    locales_dir = dest_dir / "locales"
    locales_dir.mkdir(parents=True, exist_ok=True)

    name_part = mod_id.split(".")[-1]
    title_name = name_part.replace("_", " ").title()
    desc = description.strip() or f"{title_name} extension mod for Axiom AI."

    # 1. mod.toml
    toml_content = _generate_mod_toml(mod_id, mod_type, title_name, desc, author)
    manifest_file.write_text(toml_content, encoding="utf-8")

    # Verify manifest parses correctly
    parse_manifest_file(manifest_file)

    # 2. main.py
    main_py_file = dest_dir / "main.py"
    main_py_content = _generate_main_py(mod_id, mod_type, title_name)
    main_py_file.write_text(main_py_content, encoding="utf-8")

    # 3. tests/test_<name>.py
    test_py_file = tests_dir / f"test_{name_part}.py"
    test_py_content = _generate_test_py(mod_id, mod_type)
    test_py_file.write_text(test_py_content, encoding="utf-8")

    # 4. locales/en.json
    locales_en_file = locales_dir / "en.json"
    import json
    locales_en_file.write_text(
        json.dumps({"title": title_name, "description": desc}, indent=2),
        encoding="utf-8",
    )

    logger.info("Scaffolded new %s mod '%s' at %s", mod_type, mod_id, dest_dir)
    return dest_dir
