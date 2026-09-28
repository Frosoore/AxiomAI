"""Unit tests for community.survival."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from axiom.kernel.context import ModContext
from axiom.kernel.manifest import parse_manifest_file
from axiom.kernel.registry import KernelRegistry


def test_community_survival_initialization() -> None:
    """Verify that community.survival initializes properly in an isolated ModContext."""
    mod_root = Path(__file__).resolve().parent.parent
    manifest = parse_manifest_file(mod_root / "mod.toml")

    assert manifest.id == "community.survival"
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
