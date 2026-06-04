"""Tests du NarrativeWorker, coquille de threading autour de Session (Étape 7).

Depuis le Pilier 1 §5.3-bis Étape 7, le worker ne pilote plus l'Arbitrator :
il délègue à `Session.take_turn` et re-émet ses callbacks de progression en
signaux Qt. On vérifie ici ce contrat de délégation en appelant `run()` de façon
synchrone (sans démarrer de thread), avec une Session factice. Le chemin moteur
réel est couvert par test_session.py / test_arbitrator.py.
"""

from dataclasses import dataclass

import pytest

from axiom.backends.base import LLMConnectionError
from workers.narrative_worker import NarrativeWorker


@dataclass
class _Action:
    text: str
    player_id: str


class _FakeSession:
    """Session factice : enregistre les kwargs reçus et exerce les callbacks."""

    def __init__(self, result="RESULT", hero=None, raises=None):
        self._result = result
        self._hero = hero
        self._raises = raises
        self.received = None

    def take_turn(self, player_input, **kwargs):
        self.received = {"player_input": player_input, **kwargs}
        if self._raises is not None:
            raise self._raises
        # Exerce les callbacks comme le ferait le vrai Session.
        if kwargs.get("on_status"):
            kwargs["on_status"]("Generating narrative…")
        if self._hero is not None and kwargs.get("on_hero_decision"):
            kwargs["on_hero_decision"](self._hero)
        if kwargs.get("on_token"):
            kwargs["on_token"]("Hello ")
            kwargs["on_token"]("world.")
        if kwargs.get("on_status"):
            kwargs["on_status"]("Ready.")
        return self._result


def _wire(worker):
    """Connecte tous les signaux à des collecteurs ; renvoie le dict de captures."""
    caps = {"tokens": [], "status": [], "hero": [], "complete": [], "error": []}
    worker.token_received.connect(caps["tokens"].append)
    worker.status_update.connect(caps["status"].append)
    worker.hero_decision_received.connect(caps["hero"].append)
    worker.turn_complete.connect(caps["complete"].append)
    worker.error_occurred.connect(caps["error"].append)
    return caps


def test_run_forwards_session_args_and_callbacks_to_signals():
    """run() passe le texte/player_id de l'action à Session.take_turn et re-émet
    on_token/on_status/on_hero_decision en signaux Qt + turn_complete avec le résultat."""
    session = _FakeSession(result="THE_RESULT", hero="Hero strikes.")
    worker = NarrativeWorker(
        session, _Action(text="J'attaque", player_id="p1"),
        temperature=0.5, top_p=0.9, verbosity="talkative",
    )
    caps = _wire(worker)

    worker.run()  # synchrone, pas de thread

    # Les paramètres de jeu sont transmis tels quels.
    assert session.received["player_input"] == "J'attaque"
    assert session.received["player_id"] == "p1"
    assert session.received["temperature"] == 0.5
    assert session.received["top_p"] == 0.9
    assert session.received["verbosity_level"] == "talkative"

    # Les callbacks sont re-émis en signaux.
    assert caps["tokens"] == ["Hello ", "world."]
    assert "Ready." in caps["status"]
    assert caps["hero"] == ["Hero strikes."]
    assert caps["complete"] == ["THE_RESULT"]
    assert caps["error"] == []


def test_run_emits_error_signal_on_llm_connection_error():
    """Une LLMConnectionError dans take_turn est convertie en error_occurred +
    statut 'LLM connection error.' (pas de turn_complete, pas d'exception)."""
    session = _FakeSession(raises=LLMConnectionError("down"))
    worker = NarrativeWorker(session, _Action(text="x", player_id="p1"))
    caps = _wire(worker)

    worker.run()

    assert caps["complete"] == []
    assert len(caps["error"]) == 1
    assert "LLM unreachable" in caps["error"][0]
    assert "LLM connection error." in caps["status"]


def test_run_emits_error_signal_on_unexpected_error():
    """Toute autre exception devient un error_occurred générique + statut 'Error.'."""
    session = _FakeSession(raises=ValueError("boom"))
    worker = NarrativeWorker(session, _Action(text="x", player_id="p1"))
    caps = _wire(worker)

    worker.run()

    assert caps["complete"] == []
    assert len(caps["error"]) == 1
    assert "Unexpected error during turn: boom" in caps["error"][0]
    assert "Error." in caps["status"]
