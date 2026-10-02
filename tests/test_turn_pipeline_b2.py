"""Lot B2 (corrections 2026-10) — the game turn and its regressions.

- an error of a third-party mod inside the turn no longer cancels the turn: the
  mod is disabled and reported, the turn goes on (3-MODS B4, 2-PHASE0 I-6);
- the error of the turn itself (LLM unreachable) reaches the caller unchanged (K6);
- the correction loop works again and its hint is save data, rewound with the
  turn (3-MODS B3, 2-PHASE0 I-1, TICKET-105);
- `axiom.step:gather_context` runs once per turn (3-MODS I2);
- one modpack per process for sessions (K7), fork leaves the source epoch alone
  (R2-m-6), « Canon auto » is a Session post-commit step (R2-I-4),
  `community.survival` is off by default (M9), the LLM comes from the providers
  slot (M8).
"""

from __future__ import annotations

import json
import sqlite3
import textwrap
from pathlib import Path

import pytest

from axiom.arbitrator import CORRECTION_EVENT
from axiom.backends.base import LLMBackend, LLMConnectionError, LLMResponse
from axiom.config import AppConfig
from axiom.db_helpers import create_new_save
from axiom.events import EventSourcer
from axiom.kernel import KernelRegistry, bootstrap_all_mods
from axiom.schema import create_universe_db
from axiom.session import Session

HINT = "[NARRATOR HINT:"


class _ScriptLLM(LLMBackend):
    """Returns the queued responses in order (the last one repeats); records prompts."""

    def __init__(self, *responses: LLMResponse) -> None:
        self._responses = list(responses)
        self.prompts: list[list[dict]] = []

    def queue(self, *responses: LLMResponse) -> None:
        """Script the next turns (calls made before, e.g. at Session start, are forgotten)."""
        self._responses = list(responses)
        self.prompts.clear()

    def complete(self, messages, stream: bool = False, **kwargs) -> LLMResponse:
        self.prompts.append(list(messages))
        if not self._responses:
            return LLMResponse("{}", None, "stop")
        resp = self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]
        return LLMResponse(resp.narrative_text, resp.tool_call, resp.finish_reason)

    def stream_tokens(self, messages, **kwargs):
        yield self.complete(messages).narrative_text

    def is_available(self) -> bool:
        return True

    def prompt_text(self, index: int) -> str:
        return "\n".join(m["content"] for m in self.prompts[index])


class _UnreachableLLM(_ScriptLLM):
    def complete(self, messages, stream: bool = False, **kwargs) -> LLMResponse:
        raise LLMConnectionError("connection refused (test)")


def _resp(text: str, tool_call: dict | None = None) -> LLMResponse:
    return LLMResponse(text, {"elapsed_minutes": 5, **(tool_call or {})}, "stop")


@pytest.fixture
def game(tmp_path: Path):
    """A small universe with one save: player 'hero' (HP 10, Gold 5)."""
    db = str(tmp_path / "world.db")
    create_universe_db(db)
    save_id = create_new_save(db, player_name="Hero", difficulty="Normal")
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO Stat_Definitions (stat_id, name, value_type) VALUES "
            "('hp', 'HP', 'numeric'), ('gold', 'Gold', 'numeric');"
        )
        conn.execute(
            "INSERT INTO Entities (entity_id, entity_type, entity_role, name, is_active) "
            "VALUES ('hero', 'player', 'player', 'Hero', 1);"
        )
        conn.commit()
    es = EventSourcer(db)
    es.append_event(save_id, 0, "stat_set", "hero", {"entity_id": "hero", "stat_key": "HP", "value": 10})
    es.append_event(save_id, 0, "stat_set", "hero", {"entity_id": "hero", "stat_key": "Gold", "value": 5})
    es.rebuild_state_cache(save_id)
    return db, save_id


def _session(game, llm, registry=None) -> Session:
    db, save_id = game
    return Session(db, save_id, llm=llm, time_llm=llm, kernel_registry=registry)


def _write_probe_mod(root: Path, mod_id: str, body: str, contributes: str) -> None:
    mod_dir = root / mod_id
    mod_dir.mkdir(parents=True)
    (mod_dir / "mod.toml").write_text(textwrap.dedent(f"""
        [mod]
        id = "{mod_id}"
        version = "1.0.0"
        axiom_api = 1
        name = "Probe"

        [dependencies]
        "axiom.turn" = ">=1.0.0"

        [ordering]
        after = ["axiom.turn"]

        [contributes]
        {contributes}
    """), encoding="utf-8")
    (mod_dir / "main.py").write_text(textwrap.dedent(body), encoding="utf-8")


@pytest.fixture
def probe_registry(tmp_path: Path):
    """Dedicated modpack: the official mods + two faulty probe mods."""
    extra = tmp_path / "probe_mods"
    _write_probe_mod(
        extra, "probe.badfield",
        """
        def _boom(value, ctx):
            raise ValueError("probe output field bug")

        def init(ctx):
            ctx.contribute_slot("axiom.turn:output_fields", ("hunger", _boom))
        """,
        'slots = ["axiom.turn:output_fields"]',
    )
    _write_probe_mod(
        extra, "probe.badsection",
        """
        def _section(ctx):
            raise RuntimeError("probe prompt section bug")

        def init(ctx):
            ctx.contribute_slot("axiom.turn:prompt_sections", _section)
        """,
        'slots = ["axiom.turn:prompt_sections"]',
    )
    return bootstrap_all_mods(KernelRegistry(), AppConfig(), extra_dirs=[extra])


# ---------------------------------------------------------------------------
# 1. Isolation of mod contributions inside the turn / errors of the turn itself
# ---------------------------------------------------------------------------

def test_faulty_mod_contribution_is_disabled_and_turn_goes_on(game, probe_registry):
    llm = _ScriptLLM(_resp("You feel hungry.", {"hunger": 7}))
    sess = _session(game, llm, probe_registry)

    result = sess.take_turn("I eat nothing.", player_id="hero")

    assert result.narrative_text == "You feel hungry."
    assert sess.turn_id == 1
    assert set(result.faulted_mods) == {"probe.badfield", "probe.badsection"}
    assert "ValueError" in result.faulted_mods["probe.badfield"]
    faulted = probe_registry.get_faulted_mods()
    assert "probe.badfield" in faulted and "probe.badsection" in faulted
    assert not probe_registry.get_slot_contributors("axiom.turn:output_fields").count("probe.badfield")
    # The turn was committed (narrative in the Event_Log).
    events = EventSourcer(game[0]).get_events(game[1])
    assert any(e["turn_id"] == 1 and e["event_type"] == "narrative_text" for e in events)

    # Next turn: the disabled mods are no longer called, the game goes on.
    result2 = sess.take_turn("I wait.", player_id="hero")
    assert result2.faulted_mods == {}
    assert sess.turn_id == 2


def test_llm_connection_error_reaches_the_caller_unchanged(game):
    sess = _session(game, _UnreachableLLM(_resp("never")))
    with pytest.raises(LLMConnectionError, match="connection refused"):
        sess.take_turn("Hello?", player_id="hero")
    assert sess.turn_id == 0
    events = EventSourcer(game[0]).get_events(game[1])
    assert not [e for e in events if e["turn_id"] == 1]


def test_qt_worker_shows_llm_unreachable_message(game):
    from workers.narrative_worker import NarrativeWorker
    from axiom.multiplayer import PlayerAction

    sess = _session(game, _UnreachableLLM(_resp("never")))
    action = PlayerAction("hero", "Hello?", game[1], 1, "", [])
    worker = NarrativeWorker(sess, action)
    errors: list[str] = []
    worker.error_occurred.connect(errors.append)
    worker.run()  # synchronously, in this thread
    assert errors and errors[0].startswith("LLM unreachable")


def test_cli_play_shows_llm_unreachable_message(game):
    import io
    from axiom.cli.play import play_loop

    sess = _session(game, _UnreachableLLM(_resp("never")))
    out, err = io.StringIO(), io.StringIO()
    lines = iter(["Hello?", "/quit"])
    play_loop(sess, player_id="hero", read=lambda _prompt: next(lines), out=out, err=err)
    assert "[LLM unreachable]" in err.getvalue()


# ---------------------------------------------------------------------------
# 2. Correction loop: hint stored as save data, rewound with the turn
# ---------------------------------------------------------------------------

def test_correction_hint_reaches_next_turn_and_is_rewound(game):
    ghost = _resp("You swing at a ghost.", {"state_changes": [
        {"entity_id": "ghost_zz", "stat_key": "HP", "delta": -3}
    ]})
    llm = _ScriptLLM()
    sess = _session(game, llm)
    llm.queue(ghost, _resp("The air is still."))

    r1 = sess.take_turn("I attack the ghost.", player_id="hero")
    assert r1.rejected_changes and "ghost_zz" in r1.rejected_changes[0]["entity_id"]
    events = EventSourcer(game[0]).get_events(game[1])
    staged = [e for e in events if e["event_type"] == CORRECTION_EVENT]
    assert [e["turn_id"] for e in staged] == [1]

    sess.take_turn("I look around.", player_id="hero")
    assert HINT in llm.prompt_text(1) and "ghost_zz" in llm.prompt_text(1)

    # A fresh Session (new engine) still sees it: nothing lives on `self`.
    sess.rewind(1)
    llm2 = _ScriptLLM()
    sess2 = _session(game, llm2)
    llm2.queue(_resp("Again."))
    sess2.take_turn("I look around.", player_id="hero")
    assert HINT in llm2.prompt_text(0)

    # Rewind before turn 1: the rejected turn and its hint are gone.
    sess2.rewind(0)
    llm3 = _ScriptLLM()
    sess3 = _session(game, llm3)
    llm3.queue(_resp("Calm."))
    sess3.take_turn("I look around.", player_id="hero")
    assert HINT not in llm3.prompt_text(0)
    events = EventSourcer(game[0]).get_events(game[1])
    assert not [e for e in events if e["event_type"] == CORRECTION_EVENT]


def test_rule_chain_warning_is_reported(game):
    """A creator-rule cascade that reaches the depth limit (5) is flagged again
    (`rule_chain_warning` + a `rule_engine_warning` event), as before the mods split."""
    db, save_id = game
    thresholds = [5, 6, 8, 11, 15, 20]  # Gold 5 -> 6 -> 8 -> 11 -> 15 -> 20 ...
    with sqlite3.connect(db) as conn:
        for k, threshold in enumerate(thresholds):
            conn.execute(
                "INSERT INTO Rules (rule_id, priority, conditions, actions, target_entity) VALUES (?,?,?,?,?);",
                (
                    f"chain{k}", 0,
                    json.dumps({"operator": "AND", "clauses": [
                        {"stat": "Gold", "comparator": ">=", "value": threshold}]}),
                    json.dumps([{"type": "stat_change", "target": "hero", "stat": "Gold", "value": k + 1}]),
                    "hero",
                ),
            )
        conn.commit()
    llm = _ScriptLLM()
    sess = _session(game, llm)
    llm.queue(_resp("Ouch.", {"state_changes": [{"entity_id": "hero", "stat_key": "HP", "delta": -1}]}))
    result = sess.take_turn("I trip.", player_id="hero")
    assert result.rule_chain_warning is True
    events = EventSourcer(db).get_events(save_id)
    assert any(e["turn_id"] == 1 and e["event_type"] == "rule_engine_warning" for e in events)


# ---------------------------------------------------------------------------
# 3. Single orchestration: gather_context once per turn
# ---------------------------------------------------------------------------

def test_gather_context_hook_runs_once_per_turn(game):
    from axiom.kernel.loader import get_kernel_registry
    reg = get_kernel_registry()
    calls: list[int] = []
    reg.add_hook("axiom.step:gather_context", "test.counter", lambda ctx: calls.append(ctx.turn_id))
    try:
        _session(game, _ScriptLLM(_resp("Fine."))).take_turn("Hi.", player_id="hero")
    finally:
        reg.remove_hook("axiom.step:gather_context", "test.counter")
    assert calls == [1]


def test_process_turn_uses_the_turn_mod_pipeline(game):
    """ArbitratorEngine.process_turn (multiplayer ActionQueue, embedders) goes through
    the axiom.turn hook: a third-party output field is routed like in Session."""
    from axiom.arbitrator import ArbitratorEngine
    from axiom.kernel.loader import get_kernel_registry
    reg = get_kernel_registry()
    seen: list = []
    reg.add_to_slot("axiom.turn:output_fields", "test.field", ("hunger", lambda v, ctx: seen.append(v)))
    try:
        engine = ArbitratorEngine(game[0])
        engine.configure(_ScriptLLM(_resp("Hm.", {"hunger": 3})))
        engine.process_turn(game[1], 1, {"hero": "Eat."}, "sys", [])
    finally:
        reg.remove_slot_contribution("axiom.turn:output_fields", "test.field")
    assert seen == [3]


# ---------------------------------------------------------------------------
# 4. One modpack per process; fork; Canon auto; providers; survival
# ---------------------------------------------------------------------------

def test_sessions_share_the_process_modpack(game, monkeypatch):
    import axiom.kernel.loader as loader
    reg = loader.get_kernel_registry()
    calls: list = []
    monkeypatch.setattr(loader, "bootstrap_all_mods", lambda *a, **k: calls.append(1))
    s1 = _session(game, _ScriptLLM(_resp("a")))
    s2 = _session(game, _ScriptLLM(_resp("b")))
    assert s1.kernel_registry is reg and s2.kernel_registry is reg
    assert calls == []


def test_fork_does_not_bump_the_source_epoch(game):
    sess = _session(game, _ScriptLLM(_resp("x")))
    sess.take_turn("Go.", player_id="hero")
    before = sess.epoch
    sess.fork(player_name="Copy")
    assert sess.epoch == before


def test_auto_canonize_is_a_session_post_commit_step(game, monkeypatch):
    import threading
    import axiom.canonize as canonize
    from axiom.config import load_config, save_config
    from axiom.session import get_auto_canonize, set_auto_canonize

    done = threading.Event()
    calls: list[tuple] = []

    def fake_canonize(db_path, text, *, preview=True, **_kw):
        calls.append((db_path, text, preview))
        done.set()
        return {"applied": True}

    monkeypatch.setattr(canonize, "canonize_story", fake_canonize)

    sess = _session(game, _ScriptLLM(_resp("A tower rises.")))
    sess.take_turn("Look.", player_id="hero")
    assert calls == []  # off by default

    cfg = load_config()
    set_auto_canonize(cfg, True)
    save_config(cfg)
    assert get_auto_canonize(load_config()) is True
    sess.take_turn("Look again.", player_id="hero")
    assert done.wait(5)
    assert calls == [(game[0], "A tower rises.", False)]


def test_llm_backend_comes_from_the_providers_slot(monkeypatch):
    from axiom.kernel.loader import get_kernel_registry
    from axiom.session import resolve_llm_backend
    reg = get_kernel_registry()
    sentinel = object()
    reg.add_to_slot("axiom.turn:llm_backend", "test.provider", lambda *a: sentinel)
    reg.set_mod_order(["test.provider"] + list(reg.load_state.load_order))
    try:
        assert resolve_llm_backend(registry=reg) is sentinel
    finally:
        reg.remove_slot_contribution("axiom.turn:llm_backend", "test.provider")
        reg.set_mod_order(list(reg.load_state.load_order))
    assert "axiom.providers" in reg.get_slot_contributors("axiom.turn:llm_backend")


def test_community_survival_is_off_by_default_and_can_be_enabled():
    from axiom.kernel.loader import STATE_DISABLED, discover_mods, is_mod_enabled, plan_modpack

    installed = discover_mods()
    plan = plan_modpack(installed, AppConfig())
    st = plan.statuses["community.survival"]
    assert st.state == STATE_DISABLED and "default" in st.reason
    assert is_mod_enabled("community.survival", AppConfig()) is False
    assert "axiom.turn" in st.manifest.dependencies

    cfg = AppConfig()
    cfg.mod_settings["community.survival"] = {"enabled": True}
    plan2 = plan_modpack(installed, cfg)
    assert "community.survival" in plan2.load_order
    assert plan2.load_order.index("community.survival") > plan2.load_order.index("axiom.turn")
