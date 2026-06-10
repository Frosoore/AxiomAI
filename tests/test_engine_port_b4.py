"""tests/test_engine_port_b4.py

B4 — fin du portage moteur : la logique des derniers workers Qt vit dans
`axiom/` (création entité joueur, régénération de variante, Mini-Dico, file
multijoueur). Pur moteur, LLM/arbitrator factices.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from axiom.schema import create_universe_db


@pytest.fixture
def db(tmp_path: Path) -> str:
    path = tmp_path / "u.db"
    create_universe_db(str(path))
    return str(path)


# ---------------------------------------------------------------------------
# create_player_entity
# ---------------------------------------------------------------------------

class TestCreatePlayerEntity:
    def test_creation_avec_stats_par_defaut(self, db):
        from axiom.db_helpers import create_player_entity

        with sqlite3.connect(db) as conn:
            conn.execute(
                "INSERT INTO Stat_Definitions (stat_id, name, description, value_type, parameters) "
                "VALUES ('health', 'Health', '', 'numeric', '{}');")
            conn.commit()

        eid = create_player_entity(db, "Aria la Rouge", "Voyageuse.")
        assert eid == "aria_la_rouge"
        with sqlite3.connect(db) as conn:
            etype, origin = conn.execute(
                "SELECT entity_type, origin FROM Entities WHERE entity_id = ?;", (eid,)
            ).fetchone()
            stats = conn.execute(
                "SELECT stat_key, stat_value FROM Entity_Stats WHERE entity_id = ?;", (eid,)
            ).fetchall()
        assert etype == "player"
        assert origin == "runtime"  # jamais touché par le hot reload (§7.6)
        assert stats == [("Health", "10")]

    def test_collision_desambiguisee(self, db):
        from axiom.db_helpers import create_player_entity

        first = create_player_entity(db, "Bob")
        second = create_player_entity(db, "Bob")
        assert first == "bob"
        assert second != first and second.startswith("bob_")

    def test_nom_vide_fallback(self, db):
        """L'ancienne version Qt levait NameError ici (datetime non importé)."""
        from axiom.db_helpers import create_player_entity

        eid = create_player_entity(db, "!!!")
        assert eid.startswith("player_")


# ---------------------------------------------------------------------------
# regenerate_variant
# ---------------------------------------------------------------------------

class TestRegenerateVariant:
    def _seed_turn(self, db: str, save_id: str = "s1") -> None:
        with sqlite3.connect(db) as conn:
            conn.execute(
                "INSERT INTO Saves (save_id, player_name, difficulty, last_updated, player_persona) "
                "VALUES (?, 'Hero', 'Normal', '2026-06-10', '');", (save_id,))
            conn.execute(
                "INSERT INTO Event_Log (save_id, turn_id, event_type, target_entity, payload) "
                "VALUES (?, 3, 'narrative_text', 'world', ?);",
                (save_id, json.dumps({"active": 0, "variants": ["Texte original."]})))
            conn.commit()

    def test_variante_ajoutee_et_active(self, db):
        from axiom.regenerate import regenerate_variant

        self._seed_turn(db)

        class FakeLLM:
            def stream_tokens(self, prompt, **kw):
                # Le system prompt ne doit plus exiger de tool-call.
                sys = next(m for m in prompt if m["role"] == "system")
                assert "Do NOT output any JSON tool calls" in sys["content"] or \
                       "You MUST end your response" not in sys["content"]
                yield "Nouvelle "
                yield "variante."

        tokens: list[str] = []
        history = [
            {"event_type": "user_input", "payload": {"text": "J'avance."}},
            {"event_type": "narrative_text",
             "payload": {"active": 0, "variants": ["Texte original."]}},
        ]
        out = regenerate_variant(
            FakeLLM(), db, "s1", 3, history,
            system_prompt="You MUST end your response with a JSON block",
            user_message="J'avance.", on_token=tokens.append)

        assert out == "Nouvelle variante."
        assert tokens == ["Nouvelle ", "variante."]
        with sqlite3.connect(db) as conn:
            payload = json.loads(conn.execute(
                "SELECT payload FROM Event_Log WHERE save_id='s1' AND turn_id=3;"
            ).fetchone()[0])
        assert payload["variants"] == ["Texte original.", "Nouvelle variante."]
        assert payload["active"] == 1

    def test_payload_legacy_converti(self, db):
        from axiom.regenerate import append_variant

        with sqlite3.connect(db) as conn:
            conn.execute(
                "INSERT INTO Saves (save_id, player_name, difficulty, last_updated, player_persona) "
                "VALUES ('s1', 'Hero', 'Normal', '2026-06-10', '');")
            conn.execute(
                "INSERT INTO Event_Log (save_id, turn_id, event_type, target_entity, payload) "
                "VALUES ('s1', 1, 'narrative_text', 'world', ?);",
                (json.dumps({"text": "Ancien format."}),))
            conn.commit()

        assert append_variant(db, "s1", 1, "Variante.") is True
        with sqlite3.connect(db) as conn:
            payload = json.loads(conn.execute(
                "SELECT payload FROM Event_Log WHERE turn_id=1;").fetchone()[0])
        assert payload == {"active": 1, "variants": ["Ancien format.", "Variante."]}

    def test_tour_sans_narratif(self, db):
        from axiom.regenerate import append_variant
        assert append_variant(db, "s1", 99, "x") is False


# ---------------------------------------------------------------------------
# mini_dico
# ---------------------------------------------------------------------------

def test_answer_lore_question():
    from axiom.mini_dico import answer_lore_question

    class FakeVM:
        def query(self, save_id, question, k):
            assert (save_id, k) == ("s1", 5)
            return [{"text": "La Guilde contrôle le port."}]

    class FakeLLM:
        def complete(self, messages, **kw):
            joined = " ".join(m["content"] for m in messages)
            assert "La Guilde contrôle le port." in joined
            return SimpleNamespace(narrative_text="Réponse encyclopédique.")

    out = answer_lore_question(FakeLLM(), FakeVM(), "Qui contrôle le port ?", "s1")
    assert out == "Réponse encyclopédique."


def test_answer_lore_question_repli_si_vide():
    from axiom.mini_dico import answer_lore_question

    class FakeVM:
        def query(self, *a, **k):
            return []

    class FakeLLM:
        def complete(self, *a, **k):
            return SimpleNamespace(narrative_text="")

    assert "(No answer" in answer_lore_question(FakeLLM(), FakeVM(), "?", "s1")


# ---------------------------------------------------------------------------
# multiplayer ActionQueue
# ---------------------------------------------------------------------------

def test_action_queue_sequentielle_et_stop():
    import threading

    from axiom.multiplayer import ActionQueue, PlayerAction

    order: list[str] = []

    class FakeArbitrator:
        def process_turn(self, *, save_id, turn_id, intents,
                         universe_system_prompt, history,
                         stream_token_callback, temperature, top_p, verbosity_level):
            stream_token_callback("tok")
            player_entity_id = next(iter(intents))
            order.append(player_entity_id)
            return f"result-{player_entity_id}"

    q = ActionQueue(FakeArbitrator())
    tokens: list[tuple[str, str]] = []
    done: list[tuple[object, str]] = []
    both_done = threading.Event()

    def on_complete(result, pid):
        done.append((result, pid))
        if len(done) == 2:
            both_done.set()

    def action(pid: str) -> PlayerAction:
        return PlayerAction(player_id=pid, text="go", save_id="s1", turn_id=1,
                            universe_system_prompt="GM", history=[])

    q.enqueue(action("p1"))
    q.enqueue(action("p2"))
    worker = threading.Thread(target=lambda: q.run_loop(
        on_token=lambda t, pid: tokens.append((t, pid)),
        on_complete=on_complete,
    ))
    worker.start()
    # stop() une fois les deux actions résolues (comme le GUI à la fermeture) —
    # un stop() prématuré abandonne la file, c'est le contrat historique.
    assert both_done.wait(timeout=5)
    q.stop()
    worker.join(timeout=5)
    assert not worker.is_alive()

    assert order == ["p1", "p2"]  # séquentiel, ordre FIFO
    assert done == [("result-p1", "p1"), ("result-p2", "p2")]
    assert tokens == [("tok", "p1"), ("tok", "p2")]


def test_action_queue_erreur_ne_tue_pas_la_boucle():
    import threading

    from axiom.multiplayer import ActionQueue, PlayerAction

    class FlakyArbitrator:
        def __init__(self):
            self.calls = 0

        def process_turn(self, **kw):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("boom")
            return "ok"

    q = ActionQueue(FlakyArbitrator())
    errors: list[tuple[str, str]] = []
    done: list[tuple[object, str]] = []
    ok_done = threading.Event()

    def on_complete(result, pid):
        done.append((result, pid))
        ok_done.set()

    a = PlayerAction(player_id="p1", text="go", save_id="s", turn_id=1,
                     universe_system_prompt="GM", history=[])
    q.enqueue(a)
    q.enqueue(a)
    worker = threading.Thread(target=lambda: q.run_loop(
        on_error=lambda msg, pid: errors.append((msg, pid)),
        on_complete=on_complete,
    ))
    worker.start()
    assert ok_done.wait(timeout=5)
    q.stop()
    worker.join(timeout=5)

    assert errors == [("boom", "p1")]
    assert done == [("ok", "p1")]  # la 2e action passe malgré l'erreur de la 1re
