"""tests/test_generation_cancel.py

TICKET-033 — retries visibles + annulation manuelle des générations :
- le backend émet un compte à rebours pendant l'attente de retry 429 ;
- l'attente (retry comme pacing) est interruptible par `cancel_event` ;
- `populate_entities` s'annule entre deux chunks (les commits restent) ;
- les tâches annulables passent par le registre (bouton de la barre de statut)
  et émettent `cancelled` (pas `error`).
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from axiom.backends.base import GenerationCancelled
from axiom.backends.gemini import GeminiClient
from axiom.schema import create_universe_db


_QUOTA_MSG = "429 RESOURCE_EXHAUSTED ... Please retry in 12.0s."


def _fake_clock(monkeypatch) -> list[float]:
    clock = {"t": 0.0}
    sleeps: list[float] = []

    def fake_sleep(s: float) -> None:
        sleeps.append(s)
        clock["t"] += s

    monkeypatch.setattr("axiom.backends.gemini.time.monotonic", lambda: clock["t"])
    monkeypatch.setattr("axiom.backends.gemini.time.sleep", fake_sleep)
    return sleeps


@pytest.fixture
def gemini():
    with patch("axiom.backends.gemini.genai.Client") as mock_cls:
        inner = MagicMock()
        mock_cls.return_value = inner
        yield GeminiClient(api_key="fake-key"), inner


# ---------------------------------------------------------------------------
# Backend : compte à rebours + interruption
# ---------------------------------------------------------------------------

def test_compte_a_rebours_emis_pendant_le_retry(gemini, monkeypatch):
    client, inner = gemini
    _fake_clock(monkeypatch)
    messages: list[str] = []
    client.on_status = messages.append

    inner.models.generate_content.side_effect = [
        Exception(_QUOTA_MSG),
        MagicMock(text="ok", candidates=[MagicMock(finish_reason="STOP")]),
    ]
    client.complete([{"role": "user", "content": "hi"}])

    countdowns = [m for m in messages if "retry in" in m]
    assert countdowns, messages
    assert "attempt 1/3" in countdowns[0]
    # Le compte à rebours décroît (tranches de 5s).
    assert "12s" in countdowns[0] or "13s" in countdowns[0]
    assert len(countdowns) >= 2


def test_annulation_pendant_l_attente_de_retry(gemini):
    client, inner = gemini
    cancel = threading.Event()
    client.cancel_event = cancel

    def raise_quota_and_request_cancel(**_kw):
        cancel.set()  # l'utilisateur clique Annuler pendant la génération
        raise Exception(_QUOTA_MSG)

    inner.models.generate_content.side_effect = raise_quota_and_request_cancel
    with pytest.raises(GenerationCancelled):
        client.complete([{"role": "user", "content": "hi"}])
    # Pas de nouvel essai après annulation.
    assert inner.models.generate_content.call_count == 1


def test_annulation_avant_l_appel(gemini):
    client, inner = gemini
    client.cancel_event = threading.Event()
    client.cancel_event.set()
    with pytest.raises(GenerationCancelled):
        client.complete([{"role": "user", "content": "hi"}])
    assert inner.models.generate_content.call_count == 0


# ---------------------------------------------------------------------------
# Moteur : annulation entre chunks (les commits restent)
# ---------------------------------------------------------------------------

def test_populate_entities_annule_entre_chunks(tmp_path: Path):
    from axiom.populate import populate_entities

    db = tmp_path / "u.db"
    create_universe_db(str(db))
    with sqlite3.connect(str(db)) as conn:
        conn.execute("INSERT INTO Universe_Meta (key, value) VALUES ('global_lore', 'Monde.');")
        conn.execute(
            "INSERT INTO Lore_Book (entry_id, category, name, keywords, content) "
            "VALUES ('l1', 'Faction', 'Guilde', '', 'Une guilde.');")
        conn.commit()  # → 2 chunks en mode auto

    cancel = threading.Event()

    class FakeLLM:
        def complete(self, *_a, **_k):
            cancel.set()  # annulation demandée pendant le 1er chunk
            return SimpleNamespace(tool_call={"entities": [
                {"name": "Le Forgeron", "entity_type": "npc"}]})

    with pytest.raises(GenerationCancelled, match="kept"):
        populate_entities(str(db), llm=FakeLLM(), cancel=cancel)

    # Le chunk 1, déjà commité, est conservé.
    with sqlite3.connect(str(db)) as conn:
        ids = {r[0] for r in conn.execute("SELECT entity_id FROM Entities;")}
    assert "le_forgeron" in ids


# ---------------------------------------------------------------------------
# Workers : registre + signal cancelled
# ---------------------------------------------------------------------------

def test_tache_annulee_emet_cancelled_pas_error(qapp_or_none=None):
    from workers.db_tasks import BaseDbTask

    executed: list[bool] = []

    class DummyGen(BaseDbTask):
        cancellable = True

        def execute(self):
            executed.append(True)
            if self.cancel_event.is_set():
                raise GenerationCancelled("stoppé net")
            return "done"

    task = DummyGen("unused.db")
    got_cancel: list[str] = []
    got_error: list[str] = []
    task.signals.cancelled.connect(got_cancel.append)
    task.signals.error.connect(got_error.append)

    task.cancel()
    task.run()
    # Annulée avant démarrage : execute() n'est jamais appelé (QA-042.3, la
    # tâche encore en file est couverte), et c'est `cancelled` qui est émis,
    # jamais `error`.
    assert executed == []
    assert len(got_cancel) == 1
    assert got_error == []


def test_tache_annulee_en_cours_emet_cancelled_pas_error(qapp_or_none=None):
    from workers.db_tasks import BaseDbTask

    class DummyGen(BaseDbTask):
        cancellable = True

        def execute(self):
            # L'annulation tombe pendant l'exécution (frontière coopérative).
            self.cancel_event.set()
            raise GenerationCancelled("stoppé net")

    task = DummyGen("unused.db")
    got_cancel: list[str] = []
    got_error: list[str] = []
    task.signals.cancelled.connect(got_cancel.append)
    task.signals.error.connect(got_error.append)

    task.run()
    assert got_cancel == ["stoppé net"]
    assert got_error == []


def test_registre_cancel_active_generations():
    from workers.db_tasks import (
        BaseDbTask,
        active_generation_count,
        cancel_active_generations,
    )

    started = threading.Event()

    class BlockingGen(BaseDbTask):
        cancellable = True

        def execute(self):
            started.set()
            if self.cancel_event.wait(timeout=5):
                raise GenerationCancelled("annulé")
            return "done"

    task = BlockingGen("unused.db")
    got: list[str] = []
    # Émis depuis le thread worker : connexion directe (pas de boucle Qt ici).
    from PySide6.QtCore import Qt
    task.signals.cancelled.connect(got.append, Qt.DirectConnection)

    worker = threading.Thread(target=task.run)
    worker.start()
    assert started.wait(timeout=5)
    assert active_generation_count() == 1  # visible par le bouton de la barre
    assert cancel_active_generations() == 1
    worker.join(timeout=5)
    assert got == ["annulé"]
    assert active_generation_count() == 0
