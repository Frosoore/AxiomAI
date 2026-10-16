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


def test_unchecking_the_world_promotes_minimal_chat_as_fallback():
    """Unchecking axiom.world promotes axiom.minimal_chat as transparent turn_pipeline
    fallback so interfaces (Qt, Web, CLI) continue running in minimal chat mode."""
    from axiom.config import AppConfig
    from axiom.kernel.loader import bootstrap_all_mods, interface_unavailable_message

    cfg = AppConfig()
    cfg.mod_settings["axiom.world"] = {"enabled": False}
    reg = bootstrap_all_mods(KernelRegistry(), cfg)
    msg = interface_unavailable_message("axiom.ui.qt", reg)
    assert msg is None
    assert "axiom.minimal_chat" in reg.load_state.load_order
    assert "axiom.ui.qt" in reg.load_state.load_order


def test_disabling_world_and_minimal_chat_tells_why_interface_cannot_start():
    """When both the world/turn pipeline and minimal chat are disabled, the launcher
    must say why turn_pipeline is missing instead of opening an unusable UI."""
    from axiom.config import AppConfig
    from axiom.kernel.loader import bootstrap_all_mods, interface_unavailable_message

    cfg = AppConfig()
    cfg.mod_settings["axiom.world"] = {"enabled": False}
    cfg.mod_settings["axiom.minimal_chat"] = {"enabled": False}
    reg = bootstrap_all_mods(KernelRegistry(), cfg)
    msg = interface_unavailable_message("axiom.ui.qt", reg)
    assert msg is not None
    assert "turn_pipeline" in msg and "--safe-mode" in msg


def test_init_failure_promotes_minimal_chat(monkeypatch):
    """K1 / K2 & TICKET-118: If axiom.turn raises in init(), axiom.minimal_chat is promoted as fallback."""
    from axiom.config import AppConfig
    import axiom.kernel.loader as loader_mod
    orig_load_mod = loader_mod.load_mod

    def fake_load_mod(path, reg, config=None, force_enabled=False):
        p = Path(path)
        if p.name == "axiom.turn" or p.stem == "axiom.turn":
            raise RuntimeError("Simulated crash in axiom.turn init()")
        return orig_load_mod(path, reg, config=config, force_enabled=force_enabled)

    monkeypatch.setattr(loader_mod, "load_mod", fake_load_mod)

    reg = loader_mod.bootstrap_all_mods(KernelRegistry(), AppConfig())
    assert "axiom.turn" not in reg.load_state.load_order
    assert "axiom.minimal_chat" in reg.load_state.load_order
    assert reg.load_state.statuses["axiom.minimal_chat"].state == loader_mod.STATE_ACTIVE
    assert "fallback" in reg.load_state.statuses["axiom.minimal_chat"].reason.lower()


def test_hot_disable_cascade_and_runtime_minimal_chat_promotion():
    """K7 & TICKET-118: If can_disable_hot is False, dependents stay next_launch (not purged).
    When turn_pipeline is purged at runtime, axiom.minimal_chat is promoted."""
    from axiom.config import AppConfig
    from axiom.kernel.loader import (
        STATE_ACTIVE,
        STATE_DISABLED,
        STATE_NEXT_LAUNCH,
        bootstrap_all_mods,
    )

    reg = bootstrap_all_mods(KernelRegistry(), AppConfig())
    load_state = reg.load_state

    # 1. Disable axiom.world with patches/raw code (can_disable_hot is False)
    load_state.contexts["axiom.world"]._registered_patches.append(("mock_func", "patch"))
    outcome = load_state.disable("axiom.world", "Test hot disable world", cascade=True)
    assert outcome == "next_launch"
    assert load_state.statuses["axiom.world"].state == STATE_NEXT_LAUNCH
    # Dependents should be marked NEXT_LAUNCH too, NOT violently purged immediately
    if "axiom.turn" in load_state.statuses:
        assert load_state.statuses["axiom.turn"].state == STATE_NEXT_LAUNCH

    # 2. Hot-disable axiom.turn directly (simulate outcome == 'now')
    outcome_turn = load_state.disable("axiom.turn", "Test hot disable turn", cascade=True)
    assert outcome_turn == "now"
    assert load_state.statuses["axiom.turn"].state == STATE_DISABLED
    # Minimal chat promoted dynamically at runtime
    assert "axiom.minimal_chat" in load_state.load_order
    assert load_state.statuses["axiom.minimal_chat"].state == STATE_ACTIVE


def test_resolver_virtual_provides_version_and_user_order():
    """K3 & K4: Version checks on virtual providers and user order prioritization."""
    from axiom.kernel.api import validate_version_spec, version_satisfies
    from axiom.kernel.manifest import ModContributes, ModDependency, ModManifest, ModOrdering
    from axiom.kernel.resolver import compute_exclusive_conflicts, resolve_load_order

    # 1. validate_version_spec rejects single-segment ~=
    with pytest.raises(ValueError, match=".*~=1.*"):
        validate_version_spec("~=1")
    assert not version_satisfies("1.2.0", "~=1")

    # 2. Virtual provides version check
    provider_manifest = ModManifest(
        id="provider.mod",
        version="1.0.0",
        axiom_api=1,
        ordering=ModOrdering(provides=["custom_pipeline"]),
    )
    consumer_manifest = ModManifest(
        id="consumer.mod",
        version="1.0.0",
        axiom_api=1,
        dependencies={"custom_pipeline": ModDependency("custom_pipeline", version_spec=">=2.0.0")},
    )
    candidates = {"provider.mod": provider_manifest, "consumer.mod": consumer_manifest}
    report = resolve_load_order(candidates)
    assert "consumer.mod" in report.disabled_mods
    assert "does not satisfy '>=2.0.0'" in report.disabled_mods["consumer.mod"]

    # 3. User order prioritization for exclusive slot conflicts
    dep_a = ModManifest(
        id="mod.base",
        version="1.0.0",
        axiom_api=1,
        provides_slots={"slot.exclusive": "exclusive"},
        contributes=ModContributes(slots=["slot.exclusive"]),
    )
    dep_b = ModManifest(
        id="mod.override",
        version="1.0.0",
        axiom_api=1,
        dependencies={"mod.base": ModDependency("mod.base")},
        contributes=ModContributes(slots=["slot.exclusive"]),
    )
    manifests = {"mod.base": dep_a, "mod.override": dep_b}
    # Topological order: base must load before override
    topo_order = ["mod.base", "mod.override"]
    # User specifies override should take precedence
    conflicts = compute_exclusive_conflicts(manifests, topo_order, user_order=["mod.override", "mod.base"])
    assert len(conflicts) == 1
    slot_name, candidates_list = conflicts[0]
    assert slot_name == "slot.exclusive"
    assert candidates_list[0] == "mod.override"  # override wins!

