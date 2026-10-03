"""tests/test_minimal_chat_mod.py

Tests the minimal chat mod (axiom.minimal_chat):
- Provides 'turn_pipeline' abstract provider for UIs when game RPG mods are disabled.
- Conflict arbitration with axiom.turn.
- Conversational LLM generation and streaming.
- Conversation history persistence and rewinding.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from axiom.backends.base import LLMBackend, LLMMessage, LLMResponse
from axiom.kernel.context import ModContext
from axiom.kernel.loader import discover_mods, is_enabled_by_default, load_mod, plan_modpack
from axiom.kernel.manifest import load_manifest
from axiom.kernel.registry import KernelRegistry
from axiom.savestore import create_save
from axiom.session import Session


class ScriptedChatLLM(LLMBackend):
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.recorded_messages: list[list[LLMMessage]] = []

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
        self.recorded_messages.append(list(messages))
        reply = self.responses.pop(0) if self.responses else "Default answer"
        return LLMResponse(narrative_text=reply)

    def stream_tokens(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        top_p: float = 1.0,
        response_format: str | None = None,
        stop_sequences: list[str] | None = None,
        max_tokens: int | None = None,
    ):
        self.recorded_messages.append(list(messages))
        reply = self.responses.pop(0) if self.responses else "Default answer"
        for word in reply.split(" "):
            yield word + " "


import axiom.paths
from axiom.compile import compile_universe
from axiom.schema import get_connection


@pytest.fixture
def harness_env(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    axiom.paths.configure(data_dir=data_dir)

    myria_src = Path(__file__).resolve().parent.parent / "universes" / "Myria"
    uni_db = compile_universe(myria_src, tmp_path / "myria.db", force=True)

    with get_connection(str(uni_db)) as conn:
        conn.execute(
            "INSERT INTO Entities (entity_id, entity_type, entity_role, name, is_active) "
            "VALUES ('player', 'player', 'player', 'Hero', 1);"
        )
        conn.commit()

    yield {
        "tmp_path": tmp_path,
        "uni_db": uni_db,
    }


def test_minimal_chat_manifest():
    mod_path = Path("mods/axiom.minimal_chat")
    manifest = load_manifest(mod_path)
    assert manifest.id == "axiom.minimal_chat"
    assert "turn_pipeline" in manifest.ordering.provides
    assert "axiom.turn" in manifest.ordering.conflicts
    assert "axiom.kernel:execute_step" in manifest.contributes.hooks
    assert not is_enabled_by_default(manifest)


def test_minimal_chat_plan_and_ui_resolution(harness_env):
    mods = discover_mods()
    # With default config (minimal_chat disabled by default)
    plan_default = plan_modpack(mods)
    assert "axiom.turn" in plan_default.load_order
    assert "axiom.minimal_chat" not in plan_default.load_order

    # With RPG mods disabled and minimal_chat enabled
    class DummyConfig:
        mod_settings = {
            "axiom.world": {"enabled": False},
            "axiom.turn": {"enabled": False},
            "axiom.inventory": {"enabled": False},
            "axiom.time": {"enabled": False},
            "axiom.rag": {"enabled": False},
            "axiom.living_memory": {"enabled": False},
            "axiom.illustrations": {"enabled": False},
            "core.stat_dynamics": {"enabled": False},
            "axiom.minimal_chat": {"enabled": True},
        }

    plan_chat = plan_modpack(mods, config=DummyConfig())
    assert "axiom.minimal_chat" in plan_chat.load_order
    assert "axiom.turn" not in plan_chat.load_order
    # UI mods should load because turn_pipeline is provided by axiom.minimal_chat
    assert "axiom.cli" in plan_chat.load_order
    assert "axiom.ui.web" in plan_chat.load_order
    assert "axiom.ui.qt" in plan_chat.load_order


def test_minimal_chat_execution_history_and_rewind(harness_env):
    env = harness_env
    save_info = create_save(env["uni_db"], "Hero", "Normal")
    save_id = save_info["save_id"]
    save_db = save_info["db_path"]

    class ChatConfig:
        mod_settings = {"axiom.minimal_chat": {"enabled": True}}

    registry = KernelRegistry()
    # Load axiom.minimal_chat into registry
    load_mod(Path("mods/axiom.minimal_chat"), registry, config=ChatConfig())

    llm = ScriptedChatLLM([
        "Hello! I am your AI conversational assistant.",
        "The weather in Paris is sunny.",
    ])

    session = Session(
        save_db,
        save_id,
        llm=llm,
        time_llm=llm,
        kernel_registry=registry,
    )

    tokens = []
    # Turn 1
    res1 = session.take_turn("Hello!", on_token=tokens.append)
    assert res1.narrative_text.strip() == "Hello! I am your AI conversational assistant."
    assert res1.game_state_tag == "dialogue"
    assert len(tokens) > 0

    # Turn 2: verify history is provided
    res2 = session.take_turn("What is the weather in Paris?")
    assert "sunny" in res2.narrative_text

    # Verify LLM messages in Turn 2 contain previous turn
    last_messages = llm.recorded_messages[-1]
    user_contents = [m.get("content", "") for m in last_messages if m.get("role") == "user"]
    assistant_contents = [m.get("content", "") for m in last_messages if m.get("role") == "assistant"]
    assert any("Hello!" in c for c in user_contents)
    assert any("What is the weather in Paris?" in c for c in user_contents)
    assert any("Hello! I am your AI conversational assistant." in c for c in assistant_contents)

    # Rewind to turn 1
    session.rewind(1)
    history_after_rewind = session._load_history()
    # After rewind to turn 1, only turn 1 remains in history
    assert len(history_after_rewind) >= 2
    assistant_msgs = [m.get("content", "") for m in history_after_rewind if m.get("role") == "assistant"]
    assert any("Hello! I am your AI conversational assistant." in c for c in assistant_msgs)
    assert not any("sunny" in c for c in assistant_msgs)


def test_safe_mode_is_interface_plus_minimal_chat():
    """Owner decision 2026-10-03: safe mode = the shipped interfaces + the minimal chat."""
    from axiom.config import AppConfig
    from axiom.kernel.loader import interface_unavailable_message, set_safe_mode

    set_safe_mode(True)
    try:
        reg = KernelRegistry()
        from axiom.kernel.loader import bootstrap_all_mods
        bootstrap_all_mods(reg, AppConfig())
        active = set(reg.load_state.load_order)
        assert active == {"axiom.minimal_chat", "axiom.ui.qt", "axiom.ui.web", "axiom.cli", "axiom.providers"}
        assert reg.has_hook("axiom.kernel:execute_step")
        assert interface_unavailable_message("axiom.ui.qt", reg) is None
    finally:
        set_safe_mode(False)


def test_unchecking_the_world_tells_why_the_interface_cannot_start():
    """Unchecking axiom.world takes the turn pipeline down: the launcher must say so
    (and how to repair) instead of opening an interface where every turn fails."""
    from axiom.config import AppConfig
    from axiom.kernel.loader import bootstrap_all_mods, interface_unavailable_message

    cfg = AppConfig()
    cfg.mod_settings["axiom.world"] = {"enabled": False}
    reg = bootstrap_all_mods(KernelRegistry(), cfg)
    msg = interface_unavailable_message("axiom.ui.qt", reg)
    assert msg is not None
    assert "turn_pipeline" in msg and "--safe-mode" in msg
