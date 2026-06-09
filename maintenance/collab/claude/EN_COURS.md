# EN_COURS — côté Claude (utilisateur)

> Écrit **uniquement par Claude Code**. Le pote (Gemini) le **lit**, ne l'édite jamais.
> Tenir à jour : déclarer ici les fichiers/modules en cours de modif **avant** d'y toucher ;
> retirer la ligne une fois mergé (pas de réservation périmée).

**Branche courante :** `dev-0`
**Chantier :** Pilier 2 — Universe-as-Code (doc §7 + annexe C.1) — MVP cœur

## Fichiers / modules que je touche en ce moment

| Fichier / module        | Type de modif        | Depuis (date) | Note pour le pote |
|-------------------------|----------------------|---------------|-------------------|
| `axiom/compile.py`      | création (arbo→.db)  | 2026-06-09    | nouveau module moteur, zéro Qt |
| `axiom/decompile.py`    | création (.db→arbo)  | 2026-06-09    | nouveau module moteur, zéro Qt |
| `axiom/package.py`      | création (.axiom v2 + compat v1) | 2026-06-09 | zéro Qt ; touche le **format `.axiom`** |
| `axiom/cli/compile_cmd.py` | création (sous-cmd compile/decompile/pack/import) | 2026-06-09 | nouveau |
| `axiom/cli/main.py`     | + sous-cmd compile/decompile/pack/import | 2026-06-09 | n'ajoute que des sous-parsers |
| `requirements.txt`      | + `tomlkit`          | 2026-06-09    | nouvelle dépendance (écriture TOML) |
| `tests/test_universe_as_code.py` | création (26 tests) | 2026-06-09 | nouveau fichier de tests |
| `axiom/saves.py`        | création (éditeur de saves Phase 6) | 2026-06-09 | zéro Qt ; lit Event_Log/State_Cache/Timeline |
| `axiom/events.py`       | + `state_at` + fix replay tour 0 | 2026-06-09 | **fichier moteur partagé** — `start_turn_id=-1` dans le replay (inclut genesis). Préviens si tu touches l'event-sourcing |
| `axiom/cli/saves_cmd.py`| création (sous-cmd save-*) | 2026-06-09 | nouveau |
| `axiom/cli/play.py`     | + `_resolve_playable_db` (db/dossier/.axiom) | 2026-06-09 | `play` accepte toutes les formes d'univers |
| `tests/test_saves_editing.py` | création (15 tests) | 2026-06-09 | nouveau fichier de tests |
| `axiom/schema.py`       | + `save_id` à `Active_Modifiers` + migration | 2026-06-09 | **schéma partagé** (TICKET-024) — colonne ajoutée, FK Saves. Préviens si tu touches le schéma |
| `axiom/modifiers.py`    | filtrage par `save_id` partout | 2026-06-09 | TICKET-024 ; `apply/tick/add/_fetch` scopés save |
| `axiom/arbitrator.py`   | `_fetch_effective_stats` filtre modifiers par `save_id` | 2026-06-09 | **fichier moteur partagé** (1 requête) |
| `axiom/session.py`      | rebuild State_Cache après run Chronicler | 2026-06-09 | **temps-causal-adjacent** (TICKET-006) — 2 lignes après `chronicler.run` |
| `axiom/universe.py`     | `Universe.load` lit `universe_name` | 2026-06-09 | TICKET-023 (1 ligne) |
| `axiom/db_helpers.py`   | branche `migrate_active_modifiers_table` | 2026-06-09 | dans create_new_save/load_saves |
| `workers/hardcore_worker.py` | DELETE modifiers par `save_id` | 2026-06-09 | TICKET-024 |
| `tests/test_ticket_fixes.py` | création (9 tests) | 2026-06-09 | nouveau (006/023/024) |

## Fichiers chauds que je m'apprête à toucher en profondeur (préviens avant)

- `workers/import_export_worker.py` — refonte `.axiom` v1→v2 (Phase 4). Touche le **format `.axiom`** (zone de
  collision déclarée). Pas de bump de `axiom/schema.py` prévu. Préviens-moi si tu vises le même format/schéma.

## Fini / mergé récemment (info pour le pote)

- _(rien)_
