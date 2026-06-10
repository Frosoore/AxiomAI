"""axiom.saves — édition de sauvegardes (créables/modifiables par humain ou LLM).

Pilier 2, Phase 6. Décisions actées (cf. maintenance/B2-…/TODO.md) :
- **D1** : le journal `Event_Log` reste la **source de vérité** (il fait tourner le rewind).
  L'édition se fait *par-dessus* : on **matérialise** l'état à un point (replay), on **forke**
  (journal tronqué), et on **importe** un état édité comme une **nouvelle** save (events « genesis »
  au tour 0). Jamais d'édition directe d'un dérivé (State_Cache/Snapshots).
- **D3** : une save importée démarre avec une **mémoire vectorielle vide** (se remplit en jouant).

Sélecteur de point : par **tour** (`at_turn`) ou par **temps in-game en minutes** (`at_minute`,
résolu via la table `Timeline`). Zéro dépendance Qt.

Format texte éditable : `save_state.toml`
    [save]      player_name / difficulty / player_persona
    [point]     turn_id / in_game_minutes   (informatif à l'export)
    [state.<entity_id>]   stat = "valeur"     (état effectif des entités)
    [[inventory]]         entity_id / item_id / quantity
    [[modifiers]]         entity_id / stat_key / delta / minutes_remaining
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Any

import tomlkit

from axiom.db_helpers import create_new_save
from axiom.events import EventSourcer
from axiom.schema import get_connection


class SaveError(Exception):
    """Erreur d'édition/lecture de sauvegarde."""


# ---------------------------------------------------------------------------
# Résolution d'un point (tour ou minute in-game)
# ---------------------------------------------------------------------------

def _max_turn(conn: sqlite3.Connection, save_id: str) -> int:
    row = conn.execute(
        "SELECT MAX(turn_id) FROM Event_Log WHERE save_id = ?;", (save_id,)
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def resolve_point(
    db_path: str,
    save_id: str,
    *,
    at_turn: int | None = None,
    at_minute: int | None = None,
) -> int:
    """Résout un sélecteur (tour ou minute in-game) en `turn_id`.

    - `at_turn` : utilisé tel quel.
    - `at_minute` : dernier tour dont `Timeline.in_game_time <= at_minute`.
    - aucun : dernier tour de la save.
    """
    if at_turn is not None and at_minute is not None:
        raise SaveError("Préciser soit at_turn, soit at_minute, pas les deux.")
    with get_connection(db_path) as conn:
        if at_turn is not None:
            return int(at_turn)
        if at_minute is not None:
            row = conn.execute(
                "SELECT MAX(turn_id) FROM Timeline WHERE save_id = ? AND in_game_time <= ?;",
                (save_id, int(at_minute)),
            ).fetchone()
            return int(row[0]) if row and row[0] is not None else 0
        return _max_turn(conn, save_id)


def _in_game_minutes_at(conn: sqlite3.Connection, save_id: str, turn_id: int) -> int:
    row = conn.execute(
        "SELECT in_game_time FROM Timeline WHERE save_id = ? AND turn_id <= ? "
        "ORDER BY turn_id DESC LIMIT 1;",
        (save_id, turn_id),
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


# ---------------------------------------------------------------------------
# Matérialisation de l'état (lecture)
# ---------------------------------------------------------------------------

def materialize_state(
    db_path: str,
    save_id: str,
    *,
    at_turn: int | None = None,
    at_minute: int | None = None,
) -> dict[str, Any]:
    """Matérialise l'état d'une save à un point donné (par replay du journal).

    Les stats par entité = stats de base de l'univers (`Entity_Stats`) recouvertes
    par l'état rejoué jusqu'au point (`State_Cache` logique). Inventaire et modifiers
    sont l'état courant (tables non event-sourcées).
    """
    turn_id = resolve_point(db_path, save_id, at_turn=at_turn, at_minute=at_minute)
    sourcer = EventSourcer(db_path)
    replayed = sourcer.state_at(save_id, up_to_turn_id=turn_id)

    with get_connection(db_path) as conn:
        conn.row_factory = sqlite3.Row
        save_row = conn.execute(
            "SELECT player_name, difficulty, player_persona FROM Saves WHERE save_id = ?;",
            (save_id,),
        ).fetchone()
        if save_row is None:
            raise SaveError(f"Sauvegarde introuvable : {save_id}")

        # Stats de base (définition d'univers) par entité active.
        base: dict[str, dict[str, str]] = {}
        for r in conn.execute(
            "SELECT es.entity_id, es.stat_key, es.stat_value FROM Entity_Stats es "
            "JOIN Entities e ON e.entity_id = es.entity_id WHERE e.is_active = 1;"
        ):
            base.setdefault(r["entity_id"], {})[r["stat_key"]] = r["stat_value"]

        inventory = [
            {"entity_id": r["entity_id"], "item_id": r["item_id"], "quantity": r["quantity"]}
            for r in conn.execute(
                "SELECT entity_id, item_id, quantity FROM Items_Inventory WHERE save_id = ? "
                "ORDER BY entity_id, item_id;",
                (save_id,),
            )
        ]
        modifiers = [
            {
                "entity_id": r["entity_id"],
                "stat_key": r["stat_key"],
                "delta": r["delta"],
                "minutes_remaining": r["minutes_remaining"],
            }
            for r in conn.execute(
                "SELECT entity_id, stat_key, delta, minutes_remaining FROM Active_Modifiers "
                "WHERE save_id = ? ORDER BY entity_id, stat_key;",
                (save_id,),
            )
        ]
        in_game_minutes = _in_game_minutes_at(conn, save_id, turn_id)

    # Fusion base ⊕ état rejoué (le replay prévaut).
    entities: dict[str, dict[str, str]] = {eid: dict(stats) for eid, stats in base.items()}
    for eid, stats in replayed.items():
        entities.setdefault(eid, {}).update(stats)

    return {
        "save": {
            "player_name": save_row["player_name"],
            "difficulty": save_row["difficulty"],
            "player_persona": save_row["player_persona"] or "",
        },
        "point": {"turn_id": turn_id, "in_game_minutes": in_game_minutes},
        "entities": entities,
        "inventory": inventory,
        "modifiers": modifiers,
    }


# ---------------------------------------------------------------------------
# Export / import TOML
# ---------------------------------------------------------------------------

def export_save_state(
    db_path: str,
    save_id: str,
    out_path: str | Path,
    *,
    at_turn: int | None = None,
    at_minute: int | None = None,
) -> Path:
    """Exporte l'état matérialisé d'une save vers un `save_state.toml` éditable."""
    state = materialize_state(db_path, save_id, at_turn=at_turn, at_minute=at_minute)
    doc = tomlkit.document()

    save_tbl = tomlkit.table()
    save_tbl["player_name"] = state["save"]["player_name"]
    save_tbl["difficulty"] = state["save"]["difficulty"]
    save_tbl["player_persona"] = state["save"]["player_persona"]
    doc["save"] = save_tbl

    point_tbl = tomlkit.table()
    point_tbl["turn_id"] = state["point"]["turn_id"]
    point_tbl["in_game_minutes"] = state["point"]["in_game_minutes"]
    doc["point"] = point_tbl

    state_tbl = tomlkit.table()
    for eid, stats in state["entities"].items():
        ent = tomlkit.table()
        for k, v in stats.items():
            ent[k] = v
        state_tbl[eid] = ent
    doc["state"] = state_tbl

    if state["inventory"]:
        inv = tomlkit.aot()
        for it in state["inventory"]:
            t = tomlkit.table()
            t["entity_id"] = it["entity_id"]
            t["item_id"] = it["item_id"]
            t["quantity"] = it["quantity"]
            inv.append(t)
        doc["inventory"] = inv

    if state["modifiers"]:
        mods = tomlkit.aot()
        for m in state["modifiers"]:
            t = tomlkit.table()
            t["entity_id"] = m["entity_id"]
            t["stat_key"] = m["stat_key"]
            t["delta"] = m["delta"]
            t["minutes_remaining"] = m["minutes_remaining"]
            mods.append(t)
        doc["modifiers"] = mods

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(tomlkit.dumps(doc), encoding="utf-8", newline="")
    return out_path


def _load_state_toml(path: str | Path) -> dict[str, Any]:
    import tomllib
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except (tomllib.TOMLDecodeError, OSError) as exc:
        raise SaveError(f"save_state.toml invalide : {exc}") from exc


def import_save_state(
    db_path: str,
    state_path: str | Path,
    *,
    player_name: str | None = None,
) -> str:
    """Crée une **nouvelle** save jouable à partir d'un `save_state.toml`.

    Sème l'état via des events « genesis » au tour 0 (entity_create + stat_set),
    puis matérialise State_Cache, l'inventaire, les modifiers et une entrée Timeline.
    Mémoire vectorielle vide (D3). Retourne le nouveau save_id.
    """
    data = _load_state_toml(state_path)
    save_meta = data.get("save", {})
    name = player_name or save_meta.get("player_name", "Hero")
    difficulty = save_meta.get("difficulty", "Normal")
    persona = save_meta.get("player_persona", "")

    save_id = create_new_save(db_path, name, difficulty, persona)
    sourcer = EventSourcer(db_path)

    # Events genesis au tour 0.
    events: list[tuple[str, int, str, str, dict]] = []
    for eid, stats in data.get("state", {}).items():
        events.append((save_id, 0, "entity_create", eid, {"entity_id": eid}))
        for stat_key, value in stats.items():
            events.append((
                save_id, 0, "stat_set", eid,
                {"entity_id": eid, "stat_key": stat_key, "value": str(value)},
            ))
    if events:
        sourcer.append_events_batch(events)
    sourcer.rebuild_state_cache(save_id)

    in_game_minutes = int(data.get("point", {}).get("in_game_minutes", 0))
    try:
        with get_connection(db_path) as conn:
            for it in data.get("inventory", []):
                conn.execute(
                    "INSERT INTO Items_Inventory (save_id, entity_id, item_id, quantity) "
                    "VALUES (?, ?, ?, ?);",
                    (save_id, it["entity_id"], it["item_id"], int(it.get("quantity", 1))),
                )
            for m in data.get("modifiers", []):
                conn.execute(
                    "INSERT INTO Active_Modifiers "
                    "(modifier_id, save_id, entity_id, stat_key, delta, minutes_remaining) "
                    "VALUES (?, ?, ?, ?, ?, ?);",
                    (str(uuid.uuid4()), save_id, m["entity_id"], m["stat_key"],
                     float(m["delta"]), int(m.get("minutes_remaining", 0))),
                )
            conn.execute(
                "INSERT INTO Timeline (save_id, turn_id, in_game_time, description) "
                "VALUES (?, ?, ?, ?);",
                (save_id, 0, in_game_minutes, "Save importée"),
            )
            conn.commit()
    except (sqlite3.Error, KeyError) as exc:
        raise SaveError(f"Import impossible (référence invalide ?) : {exc}") from exc

    sourcer.take_snapshot(save_id, 0)
    return save_id


# ---------------------------------------------------------------------------
# Correction d'une save existante (édition en place, append-only)
# ---------------------------------------------------------------------------

def apply_correction(
    db_path: str,
    save_id: str,
    patch: dict[str, Any],
    *,
    at_turn: int | None = None,
) -> int:
    """Applique une correction à une save **existante** sans réécrire le passé.

    Les changements de stats deviennent des events `manual_edit` (au tour choisi, défaut =
    dernier tour) → le journal reste cohérent et append-only, le rewind est préservé, et
    l'édition est tracée. L'inventaire et les modifiers (non event-sourcés) sont écrits
    directement.

    `patch` = {
        "entities":  {entity_id: {stat_key: "valeur", ...}},   # stat_set via manual_edit
        "inventory": [{entity_id, item_id, quantity}, ...],     # upsert (quantity 0 → retrait)
        "modifiers": [{entity_id, stat_key, delta, minutes_remaining}, ...],  # ajoutés
    }

    Returns:
        Le `turn_id` auquel la correction a été apposée.
    """
    turn_id = resolve_point(db_path, save_id, at_turn=at_turn)
    sourcer = EventSourcer(db_path)

    with get_connection(db_path) as conn:
        if conn.execute("SELECT 1 FROM Saves WHERE save_id = ?;", (save_id,)).fetchone() is None:
            raise SaveError(f"Sauvegarde introuvable : {save_id}")

    events: list[tuple[str, int, str, str, dict]] = []
    for eid, stats in patch.get("entities", {}).items():
        for stat_key, value in stats.items():
            events.append((
                save_id, turn_id, "manual_edit", eid,
                {"entity_id": eid, "stat_key": stat_key, "value": str(value)},
            ))
    if events:
        sourcer.append_events_batch(events)

    try:
        with get_connection(db_path) as conn:
            for it in patch.get("inventory", []):
                qty = int(it.get("quantity", 1))
                if qty <= 0:
                    conn.execute(
                        "DELETE FROM Items_Inventory WHERE save_id = ? AND entity_id = ? AND item_id = ?;",
                        (save_id, it["entity_id"], it["item_id"]),
                    )
                else:
                    conn.execute(
                        "INSERT OR REPLACE INTO Items_Inventory (save_id, entity_id, item_id, quantity) "
                        "VALUES (?, ?, ?, ?);",
                        (save_id, it["entity_id"], it["item_id"], qty),
                    )
            for m in patch.get("modifiers", []):
                conn.execute(
                    "INSERT INTO Active_Modifiers "
                    "(modifier_id, save_id, entity_id, stat_key, delta, minutes_remaining) "
                    "VALUES (?, ?, ?, ?, ?, ?);",
                    (str(uuid.uuid4()), save_id, m["entity_id"], m["stat_key"],
                     float(m["delta"]), int(m.get("minutes_remaining", 0))),
                )
            conn.commit()
    except (sqlite3.Error, KeyError) as exc:
        raise SaveError(f"Correction impossible (référence invalide ?) : {exc}") from exc

    sourcer.rebuild_state_cache(save_id)
    return turn_id


def diff_save_states(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Calcule le patch de correction entre deux états `save_state.toml` parsés.

    Sert au flux « éditer la save » : on exporte l'état, l'utilisateur modifie
    le TOML, et seules les **différences** sont apposées via `apply_correction`
    (sinon chaque stat inchangée deviendrait un event `manual_edit` parasite).

    - stats : valeurs modifiées ou ajoutées (la suppression d'une stat n'existe
      pas dans le modèle de correction → ignorée) ;
    - inventaire : quantités modifiées/ajoutées ; une ligne disparue → quantité 0
      (= retrait) ;
    - modifiers : seuls les **nouveaux** sont retenus (la correction ne sait
      qu'ajouter des modifiers).
    """
    entities: dict[str, dict[str, str]] = {}
    state_before = before.get("state", {})
    for eid, stats in after.get("state", {}).items():
        prior = state_before.get(eid, {})
        changed = {k: v for k, v in stats.items() if str(prior.get(k)) != str(v)}
        if changed:
            entities[eid] = changed

    inv_before = {
        (i["entity_id"], i["item_id"]): int(i.get("quantity", 1))
        for i in before.get("inventory", [])
    }
    inv_after = {
        (i["entity_id"], i["item_id"]): int(i.get("quantity", 1))
        for i in after.get("inventory", [])
    }
    inventory = [
        {"entity_id": eid, "item_id": iid, "quantity": qty}
        for (eid, iid), qty in inv_after.items()
        if inv_before.get((eid, iid)) != qty
    ]
    inventory += [
        {"entity_id": eid, "item_id": iid, "quantity": 0}
        for (eid, iid) in inv_before.keys() - inv_after.keys()
    ]

    def _mod_key(m: dict) -> tuple:
        return (m["entity_id"], m["stat_key"], float(m["delta"]),
                int(m.get("minutes_remaining", 0)))

    known = {_mod_key(m) for m in before.get("modifiers", [])}
    modifiers = [m for m in after.get("modifiers", []) if _mod_key(m) not in known]

    return {"entities": entities, "inventory": inventory, "modifiers": modifiers}


def apply_correction_file(db_path: str, save_id: str, patch_path: str | Path, *, at_turn: int | None = None) -> int:
    """Charge un fichier TOML (mêmes sections que save_state.toml) et l'applique en correction."""
    data = _load_state_toml(patch_path)
    patch = {
        "entities": data.get("state", {}),
        "inventory": data.get("inventory", []),
        "modifiers": data.get("modifiers", []),
    }
    return apply_correction(db_path, save_id, patch, at_turn=at_turn)


# ---------------------------------------------------------------------------
# Fork (découpe du journal à un point)
# ---------------------------------------------------------------------------

def fork_save(
    db_path: str,
    save_id: str,
    *,
    at_turn: int | None = None,
    at_minute: int | None = None,
    player_name: str | None = None,
) -> str:
    """Crée une nouvelle save = journal de `save_id` **tronqué** jusqu'au point choisi.

    Le journal complet jusqu'au point est copié (rewind/audit préservés) ; l'inventaire
    et les modifiers courants sont copiés tels quels. Retourne le nouveau save_id.
    """
    turn_id = resolve_point(db_path, save_id, at_turn=at_turn, at_minute=at_minute)

    with get_connection(db_path) as conn:
        conn.row_factory = sqlite3.Row
        src = conn.execute(
            "SELECT player_name, difficulty, player_persona FROM Saves WHERE save_id = ?;",
            (save_id,),
        ).fetchone()
        if src is None:
            raise SaveError(f"Sauvegarde introuvable : {save_id}")

    new_id = create_new_save(
        db_path,
        player_name or src["player_name"],
        src["difficulty"],
        src["player_persona"] or "",
    )

    with get_connection(db_path) as conn:
        conn.row_factory = sqlite3.Row
        # Copie des events jusqu'au point (event_id régénéré).
        ev_rows = conn.execute(
            "SELECT turn_id, event_type, target_entity, payload FROM Event_Log "
            "WHERE save_id = ? AND turn_id <= ? ORDER BY event_id ASC;",
            (save_id, turn_id),
        ).fetchall()
        conn.executemany(
            "INSERT INTO Event_Log (save_id, turn_id, event_type, target_entity, payload) "
            "VALUES (?, ?, ?, ?, ?);",
            [(new_id, r["turn_id"], r["event_type"], r["target_entity"], r["payload"])
             for r in ev_rows],
        )
        # Timeline jusqu'au point.
        tl_rows = conn.execute(
            "SELECT turn_id, in_game_time, description FROM Timeline "
            "WHERE save_id = ? AND turn_id <= ? ORDER BY turn_id ASC;",
            (save_id, turn_id),
        ).fetchall()
        conn.executemany(
            "INSERT INTO Timeline (save_id, turn_id, in_game_time, description) "
            "VALUES (?, ?, ?, ?);",
            [(new_id, r["turn_id"], r["in_game_time"], r["description"]) for r in tl_rows],
        )
        # Inventaire & modifiers courants (non event-sourcés → copie de l'état présent).
        inv_rows = conn.execute(
            "SELECT entity_id, item_id, quantity FROM Items_Inventory WHERE save_id = ?;",
            (save_id,),
        ).fetchall()
        conn.executemany(
            "INSERT INTO Items_Inventory (save_id, entity_id, item_id, quantity) "
            "VALUES (?, ?, ?, ?);",
            [(new_id, r["entity_id"], r["item_id"], r["quantity"]) for r in inv_rows],
        )
        mod_rows = conn.execute(
            "SELECT entity_id, stat_key, delta, minutes_remaining FROM Active_Modifiers "
            "WHERE save_id = ?;",
            (save_id,),
        ).fetchall()
        conn.executemany(
            "INSERT INTO Active_Modifiers "
            "(modifier_id, save_id, entity_id, stat_key, delta, minutes_remaining) "
            "VALUES (?, ?, ?, ?, ?, ?);",
            [(str(uuid.uuid4()), new_id, r["entity_id"], r["stat_key"], r["delta"],
              r["minutes_remaining"]) for r in mod_rows],
        )
        # Sans cette copie, les événements planifiés déjà déclenchés se
        # redéclencheraient dans la save forkée.
        fired_rows = conn.execute(
            "SELECT event_id FROM Fired_Scheduled_Events WHERE save_id = ?;",
            (save_id,),
        ).fetchall()
        conn.executemany(
            "INSERT INTO Fired_Scheduled_Events (save_id, event_id) VALUES (?, ?);",
            [(new_id, r["event_id"]) for r in fired_rows],
        )
        conn.commit()

    sourcer = EventSourcer(db_path)
    sourcer.rebuild_state_cache(new_id, up_to_turn_id=turn_id)
    sourcer.take_snapshot(new_id, turn_id)
    return new_id
