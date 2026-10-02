"""Tests d'intégration du Harnais « Golden Step » (Phase 0a).

Ce banc d'essai valide le comportement hermétique et reproductible du moteur
Axiom AI (sans réseau, sans GPU, sans LLM réel) :
- Exécution de 10 tours canoniques avec ScriptedLLMBackend
- Mutations complètes : stats, déplacements spatiaux, inventaire imbriqué, modificateurs, Session_Lore
- Vérification stricte de non-régression par SessionStateCanonicalizer :
  1. Rewind au tour 8 (diff == [])
  2. Fork au tour 8 (diff == [])
  3. Export pack_save / Import unpack_save (diff == [])
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

import axiom.paths
from axiom.compile import compile_universe
from axiom.saves import fork_save
from axiom.savestore import create_save, pack_save, unpack_save
from axiom.schema import get_connection
from axiom.session import Session
from axiom.testing.golden_harness import (
    GoldenHarnessExhaustedError,
    ScriptedLLMBackend,
    ScriptedTurnResponse,
    SessionStateCanonicalizer,
)


@pytest.fixture
def isolated_harness_env(tmp_path: Path):
    """Prépare un environnement isolé avec path injection sous tmp_path."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    axiom.paths.configure(data_dir=data_dir)
    try:
        myria_src = Path(__file__).resolve().parent.parent / "universes" / "Myria"
        uni_db = compile_universe(myria_src, tmp_path / "myria.db", force=True)

        # Injection de l'entité player dans la définition pour Myria
        with get_connection(str(uni_db)) as conn:
            conn.execute(
                "INSERT INTO Entities (entity_id, entity_type, entity_role, name, is_active) "
                "VALUES ('player', 'player', 'player', 'Hero', 1);"
            )
            conn.execute(
                "INSERT INTO Entity_Stats (entity_id, stat_key, stat_value) VALUES "
                "('player', 'Health', '100'), "
                "('player', 'Arcane Focus', '100'), "
                "('player', 'Coin', '50'), "
                "('player', 'Location', 'gilded_compass');"
            )
            conn.commit()

        yield {
            "tmp_path": tmp_path,
            "myria_src": myria_src,
            "uni_db": uni_db,
        }
    finally:
        axiom.paths.reset()


def test_scripted_llm_backend_exhaustion():
    """Vérifie que ScriptedLLMBackend lève GoldenHarnessExhaustedError si dépassé."""
    responses = [
        ScriptedTurnResponse(narrative_chunks=["First"], tool_call={})
    ]
    backend = ScriptedLLMBackend(responses)

    # 1er appel : valide
    resp = backend.complete([])
    assert resp.content == "First"

    # 2e appel : dépassement
    with pytest.raises(GoldenHarnessExhaustedError, match="ScriptedLLMBackend exhausted"):
        backend.complete([])


def test_canonicalizer_detects_mutation(isolated_harness_env):
    """Vérifie que SessionStateCanonicalizer.diff signale toute divergence d'état."""
    env = isolated_harness_env
    save_info = create_save(env["uni_db"], "Hero", "Normal")
    save_id = save_info["save_id"]
    save_db = save_info["db_path"]

    s_before = SessionStateCanonicalizer.canonicalize(save_db, save_id)

    # Mutation directe dans la base
    with get_connection(save_db) as conn:
        conn.execute(
            "UPDATE Entity_Stats SET stat_value = '80' WHERE entity_id = 'player' AND stat_key = 'Health';"
        )
        conn.commit()

    s_after = SessionStateCanonicalizer.canonicalize(save_db, save_id)
    diff = SessionStateCanonicalizer.diff(s_before, s_after)
    assert len(diff) > 0
    assert any("Health" in line for line in diff)


def test_golden_step_full_lifecycle(isolated_harness_env):
    """Scénario canonique Golden Step : 10 tours, Checkpoint S8, Rewind, Fork, Pack/Unpack."""
    env = isolated_harness_env
    tmp_path = env["tmp_path"]
    myria_src = env["myria_src"]
    uni_db = env["uni_db"]

    save_info = create_save(uni_db, "Hero", "Normal")
    save_id = save_info["save_id"]
    save_db = save_info["db_path"]

    # Script déterministe des 10 tours
    scripted_turns = [
        # T1-T3 : Mouvements spatiaux et modification de statistiques
        ScriptedTurnResponse(
            narrative_chunks=["You leave the Gilded Compass to explore Highport."],
            tool_call={
                "state_changes": [
                    {"entity_id": "player", "stat_key": "Location", "value": "highport"},
                    {"entity_id": "player", "stat_key": "Health", "delta": -5},
                ],
                "elapsed_minutes": 10,
            },
        ),
        ScriptedTurnResponse(
            narrative_chunks=["You travel to Foundry Row, expending magical energy."],
            tool_call={
                "state_changes": [
                    {"entity_id": "player", "stat_key": "Location", "value": "foundry_row"},
                    {"entity_id": "player", "stat_key": "Arcane Focus", "delta": -15},
                ],
                "elapsed_minutes": 15,
            },
        ),
        ScriptedTurnResponse(
            narrative_chunks=["Returning to the harbor, you earn payment."],
            tool_call={
                "state_changes": [
                    {"entity_id": "player", "stat_key": "Location", "value": "gilded_compass"},
                    {"entity_id": "player", "stat_key": "Coin", "delta": 25},
                ],
                "elapsed_minutes": 20,
            },
        ),
        # T4-T6 : Ajout, déplacement et imbrication d'objets (container_id non nul)
        ScriptedTurnResponse(
            narrative_chunks=["You acquire a leather satchel and crystal shards."],
            tool_call={
                "inventory_changes": [
                    {
                        "action": "add",
                        "item_id": "leather_satchel",
                        "name": "Leather Satchel",
                        "quantity": 1,
                        "is_container": True,
                        "holder_kind": "entity",
                        "holder_id": "player",
                    },
                    {
                        "action": "add",
                        "item_id": "kael_crystal_shard",
                        "name": "Kael Crystal Shard",
                        "quantity": 2,
                        "holder_kind": "entity",
                        "holder_id": "player",
                    },
                ],
                "elapsed_minutes": 10,
            },
        ),
        ScriptedTurnResponse(
            narrative_chunks=["You nest a brass spyglass into your satchel."],
            tool_call={
                "inventory_changes": [
                    {
                        "action": "add",
                        "item_id": "brass_spyglass",
                        "name": "Brass Spyglass",
                        "quantity": 1,
                        "container_id": "leather_satchel",
                        "holder_kind": "entity",
                        "holder_id": "player",
                    },
                ],
                "elapsed_minutes": 5,
            },
        ),
        ScriptedTurnResponse(
            narrative_chunks=["You nest a tunnel chart fragment into the satchel as well."],
            tool_call={
                "inventory_changes": [
                    {
                        "action": "add",
                        "item_id": "tunnel_chart_fragment",
                        "name": "Tunnel Chart Fragment",
                        "quantity": 1,
                        "container_id": "leather_satchel",
                        "holder_kind": "entity",
                        "holder_id": "player",
                    },
                ],
                "elapsed_minutes": 10,
            },
        ),
        # T7-T8 : Injection de modificateurs temporaires et tick du temps in-game
        ScriptedTurnResponse(
            narrative_chunks=["An arcane reservoir boosts your focus."],
            tool_call={
                "modifier_changes": [
                    {"entity_id": "player", "stat_key": "Arcane Focus", "delta": 15, "minutes": 120},
                ],
                "elapsed_minutes": 30,
            },
        ),
        ScriptedTurnResponse(
            narrative_chunks=["Exhaustion dampens your vitality."],
            tool_call={
                "modifier_changes": [
                    {"entity_id": "player", "stat_key": "Health", "delta": -10, "minutes": 60},
                ],
                "elapsed_minutes": 45,
            },
        ),
        # T9-T10 : Écriture de Session_Lore et stress de dérive
        ScriptedTurnResponse(
            narrative_chunks=["You learn secretive lore about the underworld."],
            tool_call={
                "session_lore_changes": [
                    {
                        "category": "Rumors",
                        "name": "Shadow Syndicate",
                        "keywords": "syndicate crime docks",
                        "content": "A clandestine organization operating in the Highport docks.",
                    }
                ],
                "state_changes": [
                    {"entity_id": "player", "stat_key": "Coin", "delta": -10},
                ],
                "elapsed_minutes": 25,
            },
        ),
        ScriptedTurnResponse(
            narrative_chunks=["You uncover divine rebel history."],
            tool_call={
                "session_lore_changes": [
                    {
                        "category": "Ancient History",
                        "name": "Fall of Ignarok",
                        "keywords": "gods flame war",
                        "content": "How the god of flame fell during the rebellion.",
                    }
                ],
                "inventory_changes": [
                    {
                        "action": "add",
                        "item_id": "marsh_tonic",
                        "name": "Marsh Tonic",
                        "quantity": 1,
                        "holder_kind": "entity",
                        "holder_id": "player",
                    }
                ],
                "elapsed_minutes": 35,
            },
        ),
    ]

    llm = ScriptedLLMBackend(scripted_turns)
    session = Session(save_db, save_id, llm=llm, time_llm=llm)

    # 1. Tours 1 à 8
    for turn_idx in range(1, 9):
        session.take_turn(f"Turn {turn_idx} action")

    assert session.turn_id == 8

    # 2. Checkpoint étalon : capturer l'état canonique à la fin du Tour 8 (S8)
    s8 = SessionStateCanonicalizer.canonicalize(save_db, save_id, at_turn=8)

    # 3. Stress & Dérive : Exécuter les Tours 9 et 10
    session.take_turn("Turn 9 action")
    session.take_turn("Turn 10 action")
    assert session.turn_id == 10

    # L'état au tour 10 doit être différent de S8
    s10 = SessionStateCanonicalizer.canonicalize(save_db, save_id)
    assert len(SessionStateCanonicalizer.diff(s8, s10)) > 0

    # 4. Rewind : session.rewind(8)
    rewind_summary = session.rewind(8)
    assert rewind_summary["rebuilt_to_turn"] == 8
    assert session.turn_id == 8

    # Vérification Rewind : comparaison avec S8
    s_rewound = SessionStateCanonicalizer.canonicalize(save_db, save_id)
    diff_rewind = SessionStateCanonicalizer.diff(s8, s_rewound)
    assert diff_rewind == [], f"Rewind drift detected:\n{''.join(diff_rewind)}"

    # 5. Fork : axiom.saves.fork_save au tour 8
    forked_id = fork_save(save_db, save_id, at_turn=8)
    s_forked = SessionStateCanonicalizer.canonicalize(save_db, forked_id)
    diff_fork = SessionStateCanonicalizer.diff(s8, s_forked)
    assert diff_fork == [], f"Fork drift detected:\n{''.join(diff_fork)}"

    # 6. Export / Unpack : pack_save puis unpack_save dans une base isolée
    archive_path = tmp_path / "golden_export.axiomsave"
    pack_save(uni_db, save_id, archive_path)
    assert archive_path.is_file()

    isolated_dir = tmp_path / "isolated"
    isolated_dir.mkdir(parents=True, exist_ok=True)
    isolated_uni_db = compile_universe(myria_src, isolated_dir / "myria.db", force=True)
    with get_connection(str(isolated_uni_db)) as conn:
        conn.execute(
            "INSERT INTO Entities (entity_id, entity_type, entity_role, name, is_active) "
            "VALUES ('player', 'player', 'player', 'Hero', 1);"
        )
        conn.execute(
            "INSERT INTO Entity_Stats (entity_id, stat_key, stat_value) VALUES "
            "('player', 'Health', '100'), "
            "('player', 'Arcane Focus', '100'), "
            "('player', 'Coin', '50'), "
            "('player', 'Location', 'gilded_compass');"
        )
        conn.commit()

    unpack_info = unpack_save(archive_path, isolated_uni_db, force=True)
    unpacked_id = unpack_info["save_id"]
    unpacked_db = unpack_info["db_path"]

    s_unpacked = SessionStateCanonicalizer.canonicalize(unpacked_db, unpacked_id)
    diff_unpack = SessionStateCanonicalizer.diff(s8, s_unpacked)
    assert diff_unpack == [], f"Unpack drift detected:\n{''.join(diff_unpack)}"


def test_transactional_turn_atomicity_on_cancellation(isolated_harness_env):
    """Vérifie l'atomicité du tour : aucune écriture disque en cas d'annulation ou d'erreur."""
    from axiom.backends.base import GenerationCancelled
    from axiom.testing.golden_harness import ScriptedLLMBackend, ScriptedTurnResponse

    env = isolated_harness_env
    save_info = create_save(env["uni_db"], "Hero", "Normal")
    save_id = save_info["save_id"]
    save_db = save_info["db_path"]

    # 1 tour valide
    llm = ScriptedLLMBackend([
        ScriptedTurnResponse(
            narrative_chunks=["First turn."],
            tool_call={
                "state_changes": [{"entity_id": "player", "stat_key": "Health", "delta": -10}],
            },
        ),
    ])
    session = Session(save_db, save_id, llm=llm, time_llm=llm)
    session.take_turn("First action")
    assert session.turn_id == 1

    # Étalon après tour 1
    s1 = SessionStateCanonicalizer.canonicalize(save_db, save_id, at_turn=1)

    # Déclenchement de l'annulation pendant le tour 2
    llm.cancel()
    with pytest.raises(GenerationCancelled):
        session.take_turn("Cancelled turn")

    # Vérifications d'intégrité
    assert session.turn_id == 1, "Le turn_id ne doit pas avoir incrémenté sur annulation"
    s_after_cancel = SessionStateCanonicalizer.canonicalize(save_db, save_id)
    diff = SessionStateCanonicalizer.diff(s1, s_after_cancel)
    assert diff == [], f"DB pollution detected after cancellation:\n{''.join(diff)}"

    # Aucune trace de turn 2 dans Event_Log ou Timeline
    with get_connection(save_db) as conn:
        events_t2 = conn.execute("SELECT COUNT(*) FROM Event_Log WHERE save_id = ? AND turn_id > 1;", (save_id,)).fetchone()[0]
        assert events_t2 == 0
        timeline_t2 = conn.execute("SELECT COUNT(*) FROM Timeline WHERE save_id = ? AND turn_id > 1;", (save_id,)).fetchone()[0]
        assert timeline_t2 == 0


def test_session_epoch_bump_and_stale_worker_discard(isolated_harness_env):
    """Vérifie l'incrémentation de session.epoch et l'invalidation des workers asynchrones obsolètes."""
    from axiom.living_memory import distil_narrative_to_memory
    from axiom.facts import get_facts

    env = isolated_harness_env
    save_info = create_save(env["uni_db"], "Hero", "Normal")
    save_id = save_info["save_id"]
    save_db = save_info["db_path"]

    llm = ScriptedLLMBackend([
        ScriptedTurnResponse(narrative_chunks=["T1"], tool_call={}),
        ScriptedTurnResponse(narrative_chunks=["T2"], tool_call={}),
    ])
    session = Session(save_db, save_id, llm=llm, time_llm=llm)
    session.take_turn("Turn 1")
    session.take_turn("Turn 2")

    initial_epoch = session.epoch

    # Rewind -> epoch + 1
    session.rewind(1)
    assert session.epoch == initial_epoch + 1

    # Fork -> the SOURCE save is only read: its epoch does not move (R2-m-6)
    session.fork()
    assert session.epoch == initial_epoch + 1

    # Simulation d'un worker asynchrone démarré à l'époque précédente
    captured_stale_epoch = session.epoch - 1  # Périmée

    # Tentative d'écriture avec époque obsolète
    result = distil_narrative_to_memory(
        llm,
        save_db,
        save_id,
        2,
        "Player discovered a secret map in the old tavern.",
        epoch=captured_stale_epoch,
        epoch_checker=lambda: session.epoch,
    )

    # Doit avoir été abandonnée silencieusement
    assert result["facts_stored"] == 0
    facts = get_facts(save_db, save_id)
    assert len(facts) == 0, "Aucun fait ne doit être écrit par un worker d'époque périmée"

