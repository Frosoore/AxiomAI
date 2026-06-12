"""tests/test_populate_resume.py

TICKET-031 — le Populate entités committe **par chunk** : un échec LLM en plein
lot (quota 429 épuisé malgré les retries du backend) conserve le travail déjà
fait, et relancer reprend là où ça s'est arrêté (ids existants sautés).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from axiom.backends.base import LLMConnectionError
from axiom.schema import create_universe_db


@pytest.fixture
def universe_db(tmp_path: Path) -> str:
    """Un .db avec global_lore + 1 entrée de lore → 2 chunks en mode auto."""
    db = tmp_path / "u.db"
    create_universe_db(str(db))
    with sqlite3.connect(str(db)) as conn:
        conn.execute("INSERT INTO Universe_Meta (key, value) VALUES ('global_lore', 'Un monde.');")
        conn.execute(
            "INSERT INTO Lore_Book (entry_id, category, name, keywords, content) "
            "VALUES ('l1', 'Faction', 'La Guilde', '', 'Une guilde.');")
        conn.commit()
    return str(db)


class _FakeLLM:
    """Renvoie un lot d'entités par appel, puis lève à partir de `fail_at`."""

    def __init__(self, batches: list[list[dict]], fail_at: int | None = None):
        self._batches = batches
        self._fail_at = fail_at
        self.calls = 0

    def complete(self, *_a, **_k):
        call = self.calls
        self.calls += 1
        if self._fail_at is not None and call >= self._fail_at:
            raise LLMConnectionError("429 RESOURCE_EXHAUSTED (simulé)")
        batch = self._batches[call] if call < len(self._batches) else []
        return SimpleNamespace(tool_call={"entities": batch})


def _entity_ids(db: str) -> set[str]:
    with sqlite3.connect(db) as conn:
        return {r[0] for r in conn.execute("SELECT entity_id FROM Entities;")}


def _run_populate(db: str, llm: _FakeLLM, monkeypatch) -> int:
    import axiom.config as config_mod
    from workers.db_tasks import PopulateEntitiesTask

    monkeypatch.setattr(config_mod, "build_llm_from_config", lambda *a, **k: llm)
    return PopulateEntitiesTask(db, mode="auto").execute()


def test_echec_en_plein_lot_conserve_les_chunks_commites(universe_db, monkeypatch):
    llm = _FakeLLM([[{"name": "Le Forgeron", "entity_type": "npc", "description": "x"}]],
                   fail_at=1)  # chunk 1 OK, chunk 2 → quota

    with pytest.raises(LLMConnectionError) as exc:
        _run_populate(universe_db, llm, monkeypatch)

    # Le travail du chunk 1 est en base, et l'erreur explique la reprise.
    assert "le_forgeron" in _entity_ids(universe_db)
    assert "1 entity(ies) already inserted" in str(exc.value)


def test_relance_reprend_sans_doublon(universe_db, monkeypatch):
    failing = _FakeLLM([[{"name": "Le Forgeron", "entity_type": "npc"}]], fail_at=1)
    with pytest.raises(LLMConnectionError):
        _run_populate(universe_db, failing, monkeypatch)

    # Relance : le LLM répond cette fois pour les deux chunks ; le Forgeron
    # revient dans la réponse mais ne doit pas être dupliqué.
    retry = _FakeLLM([
        [{"name": "Le Forgeron", "entity_type": "npc"}],
        [{"name": "La Tisseuse", "entity_type": "npc"}],
    ])
    inserted = _run_populate(universe_db, retry, monkeypatch)

    assert inserted == 1  # seule La Tisseuse est nouvelle
    assert {"le_forgeron", "la_tisseuse"} <= _entity_ids(universe_db)


def test_echec_au_premier_chunk_erreur_brute(universe_db, monkeypatch):
    llm = _FakeLLM([], fail_at=0)
    with pytest.raises(LLMConnectionError) as exc:
        _run_populate(universe_db, llm, monkeypatch)
    # Rien d'inséré → pas de message de reprise trompeur.
    assert "already inserted" not in str(exc.value)
