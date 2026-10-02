"""tests/test_kernel_resilience.py

Loader / resolver / registry resilience (review 2026-10-03, 1-NOYAU B1, I3, I4, I5, I6,
I11 and 3-MODS B5):
- a conflict or a cycle sets the faulty mods aside, the rest loads;
- the real status (with cascade) is exposed and shown by `axiom mods list`;
- init() failure -> cleanup + dependents not loaded; a hook that raises disables its mod;
- critical hooks / unguarded calls propagate; cancellation always propagates;
- kernel API and dependency versions are checked;
- user order (`mod_order`) and exclusive slot winners;
- hot disable (D-5), declared slots removed on cleanup, jobs stopped, single bootstrap;
- safe mode = no mod at all.
"""

from __future__ import annotations

import argparse
import io
import sys
import threading
from pathlib import Path

import pytest

from axiom.backends.base import GenerationCancelled
from axiom.config import AppConfig
from axiom.kernel import (
    KernelRegistry,
    ManifestError,
    ModContext,
    SlotRule,
    bootstrap_all_mods,
    disable_mod_hot,
    get_kernel_registry,
    get_load_state,
    parse_manifest_string,
    plan_modpack,
    reset_kernel_registry,
    resolve_load_order,
    set_safe_mode,
)


def write_mod(base: Path, mod_id: str, toml_extra: str = "", main: str | None = "def init(ctx):\n    pass\n",
              version: str = "1.0.0", api: int = 1) -> Path:
    d = base / mod_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "mod.toml").write_text(
        f'[mod]\nid = "{mod_id}"\nversion = "{version}"\naxiom_api = {api}\nname = "{mod_id}"\n{toml_extra}',
        encoding="utf-8",
    )
    if main is not None:
        (d / "main.py").write_text(main, encoding="utf-8")
    return d


@pytest.fixture
def mods_env(tmp_path, monkeypatch):
    """Isolated official mods folder (user mods folder is isolated by AXIOM_DATA_DIR)."""
    official = tmp_path / "official_mods"
    official.mkdir()
    monkeypatch.setenv("AXIOM_OFFICIAL_MODS_DIR", str(official))
    set_safe_mode(False)
    reset_kernel_registry()
    yield official
    set_safe_mode(False)
    reset_kernel_registry()


HOOK_MAIN = """
def init(ctx):
    ctx.register_service("{svc}", object())
    ctx.register_hook("test:tick", lambda *a: "{svc}")
"""


# ---------------------------------------------------------------------------
# B1 / B5 — conflicts and cycles no longer empty the registry; real status
# ---------------------------------------------------------------------------

def test_conflict_and_cycle_do_not_empty_registry(mods_env):
    write_mod(mods_env, "b.backend", main=HOOK_MAIN.format(svc="backend"))
    write_mod(mods_env, "f.conflict", '[ordering]\nconflicts = ["b.backend"]\n', main=HOOK_MAIN.format(svc="conflict"))
    write_mod(mods_env, "c.one", '[dependencies]\n"c.two" = "*"\n')
    write_mod(mods_env, "c.two", '[dependencies]\n"c.one" = "*"\n')
    write_mod(mods_env, "d.dependent", '[dependencies]\n"f.conflict" = ">=1.0.0"\n')

    reg = bootstrap_all_mods(KernelRegistry(), AppConfig())
    state = get_load_state(reg)

    assert reg.has_service("backend")
    assert not reg.has_service("conflict")
    assert state.get_status("b.backend").state == "active"
    assert state.get_status("f.conflict").state == "rejected"
    assert "Conflicts with 'b.backend'" in state.get_status("f.conflict").reason
    assert "Cyclic dependency detected" in state.get_status("c.one").reason
    assert "Cyclic dependency detected" in state.get_status("c.two").reason
    # cascade with the cause
    dep = state.get_status("d.dependent")
    assert dep.state == "rejected"
    assert "f.conflict" in dep.reason and "Conflicts with" in dep.reason


def test_cascade_of_user_disabled_dependency_is_visible_in_mods_list(mods_env, monkeypatch):
    from axiom.cli.mods_cmd import run_mod_list
    import axiom.config as config_mod

    write_mod(mods_env, "x.world")
    write_mod(mods_env, "x.turn", '[dependencies]\n"x.world" = ">=1.0.0"\n')
    cfg = AppConfig()
    cfg.mod_settings["x.world"] = {"enabled": False}
    monkeypatch.setattr(config_mod, "load_config", lambda *a, **k: cfg)

    plan = plan_modpack(config=cfg)
    assert plan.statuses["x.world"].state == "disabled"
    assert plan.statuses["x.turn"].state == "rejected"
    assert "'x.world' is not loaded: Disabled by the user." in plan.statuses["x.turn"].reason

    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    assert run_mod_list(argparse.Namespace()) == 0
    out = buf.getvalue()
    turn_line = next(line for line in out.splitlines() if line.startswith("x.turn"))
    assert "disabled" in turn_line and "enabled" not in turn_line
    assert "x.world' is not loaded" in out


# ---------------------------------------------------------------------------
# I4 — init() failure, faulty hooks, critical hooks
# ---------------------------------------------------------------------------

def test_init_failure_cleans_up_and_skips_dependents(mods_env):
    write_mod(mods_env, "c.partial", main=(
        "def init(ctx):\n"
        "    ctx.register_hook('k:h', lambda: 'partial')\n"
        "    ctx.declare_slot('c.partial:things', 'collect')\n"
        "    raise RuntimeError('boom')\n"
    ))
    write_mod(mods_env, "e.dependent", '[dependencies]\n"c.partial" = "*"\n', main=HOOK_MAIN.format(svc="dep"))
    write_mod(mods_env, "z.other", main=HOOK_MAIN.format(svc="other"))

    reg = bootstrap_all_mods(KernelRegistry(), AppConfig())
    state = get_load_state(reg)

    assert reg.invoke_hook("k:h") == []
    assert reg.get_slot_rule("c.partial:things") == SlotRule.COLLECT  # declaration removed too
    assert "c.partial:things" not in reg._slot_rules
    assert state.get_status("c.partial").state == "failed"
    assert "boom" in state.get_status("c.partial").reason
    assert state.get_status("e.dependent").state == "failed"
    assert "c.partial" in state.get_status("e.dependent").reason
    assert not reg.has_service("dep")
    assert reg.has_service("other")


def test_faulty_hook_disables_its_mod_and_dependents(mods_env):
    write_mod(mods_env, "a.backend", main=(
        "def init(ctx):\n"
        "    ctx.register_service('a', object())\n"
        "    ctx.register_hook('test:tick', lambda: 1 / 0)\n"
        "    ctx.register_hook('test:other', lambda: 'a-other')\n"
    ))
    write_mod(mods_env, "b.user", '[dependencies]\n"a.backend" = "*"\n', main=HOOK_MAIN.format(svc="b"))
    write_mod(mods_env, "c.healthy", main=HOOK_MAIN.format(svc="c"))

    reg = bootstrap_all_mods(KernelRegistry(), AppConfig())
    state = get_load_state(reg)

    # a raised: disabled with its dependent b during the very call; c still ran
    assert reg.invoke_hook("test:tick") == ["c"]
    assert state.get_status("a.backend").state == "faulted"
    assert "ZeroDivisionError" in state.get_status("a.backend").reason
    assert "a.backend" in reg.get_faulted_mods()
    # all of the faulty mod is gone, not only the failing hook
    assert reg.invoke_hook("test:other") == []
    assert not reg.has_service("a")
    # its dependent is disabled with it
    assert state.get_status("b.user").state == "disabled"
    assert reg.invoke_hook("test:tick") == ["c"]


def test_critical_hook_and_unguarded_call_propagate():
    reg = KernelRegistry()

    def turn(_ctx):
        raise ConnectionError("LLM unreachable")

    reg.add_hook("axiom.kernel:execute_step", "axiom.turn", turn)
    with pytest.raises(ConnectionError, match="LLM unreachable"):
        reg.execute_hook("axiom.kernel:execute_step", object())
    assert reg.get_faulted_mods() == {}  # not a mod fault: nothing disabled
    assert reg.has_hook("axiom.kernel:execute_step")

    reg.add_hook("custom:critical", "m.x", lambda: (_ for _ in ()).throw(ValueError("x")))
    with pytest.raises(ValueError):
        reg.invoke_hook_unguarded("custom:critical")
    assert reg.get_faulted_mods() == {}


def test_cancellation_is_never_swallowed():
    reg = KernelRegistry()

    def cancel():
        raise GenerationCancelled()

    reg.add_hook("test:tick", "m.cancel", cancel)
    with pytest.raises(GenerationCancelled):
        reg.invoke_hook("test:tick")
    assert reg.get_faulted_mods() == {}

    reg.add_to_slot("test:chain", "m.cancel", lambda v: (_ for _ in ()).throw(GenerationCancelled()))
    with pytest.raises(GenerationCancelled):
        reg.apply_slot_chain("test:chain", "v")


# ---------------------------------------------------------------------------
# I5 — kernel API and dependency versions
# ---------------------------------------------------------------------------

def test_api_and_dependency_versions_are_checked():
    def m(text):
        return parse_manifest_string(text)

    manifests = {
        "d.futureapi": m('[mod]\nid="d.futureapi"\nversion="1.0.0"\naxiom_api=99\n'),
        "b.b": m('[mod]\nid="b.b"\nversion="1.0.0"\naxiom_api=1\n'),
        "a.needs2": m('[mod]\nid="a.needs2"\nversion="1.0.0"\naxiom_api=1\n[dependencies]\n"b.b"=">=2.0"\n'),
        "a.needs1": m('[mod]\nid="a.needs1"\nversion="1.0.0"\naxiom_api=1\n[dependencies]\n"b.b"=">=1.0,<2"\n'),
    }
    report = resolve_load_order(manifests)
    assert "Incompatible kernel API" in report.disabled_mods["d.futureapi"]
    assert "does not satisfy '>=2.0'" in report.disabled_mods["a.needs2"]
    assert report.load_order == ["b.b", "a.needs1"]


def test_invalid_dependency_spec_is_a_manifest_error():
    with pytest.raises(ManifestError, match="Invalid version specifier"):
        parse_manifest_string('[mod]\nid="a.a"\nversion="1.0.0"\naxiom_api=1\n[dependencies]\n"b.b"="n importe quoi"\n')


def test_version_fallback_without_packaging(monkeypatch):
    import builtins
    from axiom.kernel import api

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("packaging"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert api.version_satisfies("1.2.0", ">=1.0.0,<2")
    assert not api.version_satisfies("2.0.0", ">=1.0.0,<2")
    assert api.version_satisfies("1.4.0", "~=1.2")
    with pytest.raises(ValueError):
        api.validate_version_spec("n importe quoi")


# ---------------------------------------------------------------------------
# I6 — user order and exclusive slots
# ---------------------------------------------------------------------------

EXCL_MAIN = """
def init(ctx):
    ctx.contribute_slot("t.base:backend", "{val}")
"""


def test_user_order_from_config_picks_exclusive_winner(mods_env, monkeypatch):
    from axiom.cli.mods_cmd import run_mods_conflicts
    import axiom.config as config_mod

    write_mod(mods_env, "t.base", '[provides_slots]\n"t.base:backend" = "exclusive"\n', main="def init(ctx):\n    pass\n")
    for name in ("t.alpha", "t.beta"):
        write_mod(
            mods_env, name,
            '[dependencies]\n"t.base" = "*"\n[contributes]\nslots = ["t.base:backend"]\n',
            main=EXCL_MAIN.format(val=name),
        )

    cfg = AppConfig()
    reg = bootstrap_all_mods(KernelRegistry(), cfg)
    assert reg.get_slot("t.base:backend") == "t.alpha"  # alphabetical by default, no RegistryError
    assert get_load_state(reg).get_status("t.beta").state == "active"
    assert reg.get_slot_conflicts() == {"t.base:backend": ["t.alpha", "t.beta"]}

    cfg.mod_settings["axiom.kernel"] = {"mod_order": ["t.beta", "t.alpha"]}
    reg2 = bootstrap_all_mods(KernelRegistry(), cfg)
    assert reg2.get_slot("t.base:backend") == "t.beta"
    assert get_load_state(reg2).load_order.index("t.beta") < get_load_state(reg2).load_order.index("t.alpha")

    monkeypatch.setattr(config_mod, "load_config", lambda *a, **k: cfg)
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    assert run_mods_conflicts(argparse.Namespace()) == 0
    assert "'t.base:backend': t.beta, t.alpha provide it; 't.beta' wins" in buf.getvalue()


# ---------------------------------------------------------------------------
# I3 — contexts kept, hot disable, declared slots, jobs, single bootstrap
# ---------------------------------------------------------------------------

def test_hot_disable_now_or_next_launch(mods_env):
    write_mod(mods_env, "h.hooks", '[provides_slots]\n"h.hooks:panel" = "collect"\n', main=HOOK_MAIN.format(svc="hooks"))
    write_mod(mods_env, "h.raw", "[contributes]\nraw_code = true\n", main=HOOK_MAIN.format(svc="raw"))
    write_mod(mods_env, "h.dep", '[dependencies]\n"h.hooks" = "*"\n', main=HOOK_MAIN.format(svc="dep"))

    reg = bootstrap_all_mods(KernelRegistry(), AppConfig())
    state = get_load_state(reg)
    assert set(state.contexts) == {"h.hooks", "h.raw", "h.dep"}
    assert reg.get_slot_rule("h.hooks:panel") == SlotRule.COLLECT and "h.hooks:panel" in reg._slot_rules

    assert disable_mod_hot("h.hooks", reg) == "now"
    assert not reg.has_service("hooks")
    assert "h.hooks:panel" not in reg._slot_rules  # declared slot removed (I3)
    assert state.get_status("h.dep").state == "disabled"  # cascade
    assert not reg.has_service("dep")
    assert reg.has_service("raw")  # the others were not reloaded nor touched

    assert disable_mod_hot("h.raw", reg) == "next_launch"
    assert state.get_status("h.raw").state == "disabled_next_launch"
    assert reg.has_service("raw")
    assert disable_mod_hot("h.hooks", reg) == "not_loaded"


def test_context_public_api_and_jobs_stopped_on_cleanup():
    reg = KernelRegistry()
    ctx = ModContext("j.jobs", reg)
    other = ModContext("j.other", reg)
    other.declare_slot("j.other:items", "collect")
    other.contribute_slot("j.other:items", "x")
    other.register_hook("j.other:ping", lambda: "pong")

    assert ctx.get_slot("j.other:items") == ["x"]
    assert ctx.get_slot_contributions("j.other:items") == ["x"]
    assert ctx.invoke_hook("j.other:ping") == ["pong"]

    started = threading.Event()
    stopped = threading.Event()

    def job():
        started.set()
        ctx.stop_event.wait(5)
        stopped.set()

    thread = ctx.spawn_job(job)
    assert started.wait(2)
    ctx.cleanup()
    assert stopped.is_set()
    assert not thread.is_alive()


def test_single_bootstrap_per_process(mods_env):
    counter = mods_env / "count.txt"
    write_mod(mods_env, "s.counted", main=(
        "from pathlib import Path\n"
        f"P = Path({str(counter)!r})\n"
        "def init(ctx):\n"
        "    P.write_text(str(int(P.read_text()) + 1) if P.exists() else '1')\n"
    ))
    reg1 = get_kernel_registry(AppConfig())
    reg2 = get_kernel_registry(AppConfig())
    assert reg1 is reg2
    assert counter.read_text() == "1"
    assert get_load_state().is_active("s.counted")


# ---------------------------------------------------------------------------
# I11 — safe mode = no mod at all, no privilege by name prefix
# ---------------------------------------------------------------------------

def test_safe_mode_loads_no_mod_even_axiom_prefixed(mods_env):
    write_mod(mods_env, "axiom.evil", main=HOOK_MAIN.format(svc="evil"))
    write_mod(mods_env, "core.thing", main=HOOK_MAIN.format(svc="core"))
    write_mod(mods_env, "third.party", main=HOOK_MAIN.format(svc="third"))
    set_safe_mode(True)
    reg = bootstrap_all_mods(KernelRegistry(), AppConfig())
    state = get_load_state(reg)
    assert reg._services == {}
    assert {st.state for st in state.statuses.values()} == {"safe_mode"}
