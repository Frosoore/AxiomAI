"""
tests/test_bundled_universes.py

First-launch installation of the bundled universes (TICKET-062).
"""

from pathlib import Path

import pytest

from core.bundled_universes import install_bundled_universes


@pytest.fixture
def env(tmp_path: Path) -> dict:
    """A bundle root with one valid universe, an empty library and a marker path."""
    bundle = tmp_path / "bundle"
    src = bundle / "Myria"
    (src / "lore").mkdir(parents=True)
    (src / "universe.toml").write_text('name = "Myria"\n', encoding="utf-8")
    (src / "lore" / "world.md").write_text("# Myria\n", encoding="utf-8")
    (src / ".axiom-cache").mkdir()
    (src / ".axiom-cache" / "universe.db").write_text("cache", encoding="utf-8")
    return {
        "bundle": bundle,
        "library": tmp_path / "library",
        "marker": tmp_path / "config" / "installed_bundles.txt",
    }


def _install(env: dict) -> list[str]:
    return install_bundled_universes(env["bundle"], env["library"], env["marker"])


def test_installs_universe_without_cache(env: dict) -> None:
    assert _install(env) == ["Myria"]
    dest = env["library"] / "Myria"
    assert (dest / "universe.toml").is_file()
    assert (dest / "lore" / "world.md").is_file()
    # The compile cache is rebuilt by discovery, never shipped.
    assert not (dest / ".axiom-cache").exists()
    assert "Myria" in env["marker"].read_text(encoding="utf-8")


def test_installs_only_once(env: dict) -> None:
    _install(env)
    assert _install(env) == []


def test_deleted_universe_is_not_reinstalled(env: dict) -> None:
    """A user who removes the bundled universe keeps it removed."""
    import shutil

    _install(env)
    shutil.rmtree(env["library"] / "Myria")
    assert _install(env) == []
    assert not (env["library"] / "Myria").exists()


def test_never_overwrites_existing_folder(env: dict) -> None:
    mine = env["library"] / "Myria"
    mine.mkdir(parents=True)
    (mine / "universe.toml").write_text('name = "My own Myria"\n', encoding="utf-8")

    assert _install(env) == []
    assert (mine / "universe.toml").read_text(encoding="utf-8") == 'name = "My own Myria"\n'
    # Recorded anyway: it will not be offered again later either.
    assert "Myria" in env["marker"].read_text(encoding="utf-8")


def test_ignores_non_universe_folders(env: dict) -> None:
    (env["bundle"] / "random_dir").mkdir()
    assert _install(env) == ["Myria"]
    assert not (env["library"] / "random_dir").exists()


def test_missing_bundle_root_is_a_noop(env: dict) -> None:
    assert install_bundled_universes(
        env["bundle"] / "nope", env["library"], env["marker"]
    ) == []


def test_never_raises_on_unwritable_library(env: dict) -> None:
    """Startup must survive an install failure (warning logged)."""
    env["library"].mkdir(parents=True)
    env["library"].chmod(0o500)
    try:
        assert _install(env) == []
    finally:
        env["library"].chmod(0o700)


def test_repo_bundle_contains_myria() -> None:
    """The real repo bundle ships Myria as a valid source folder."""
    from core.bundled_universes import BUNDLED_ROOT

    assert (BUNDLED_ROOT / "Myria" / "universe.toml").is_file()
