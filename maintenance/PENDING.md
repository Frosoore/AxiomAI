# PENDING — tickets à étudier

## Index des tickets

| N°        | Titre                                                          | Statut    |
|-----------|----------------------------------------------------------------|-----------|
| TICKET-001| Rework tests : lisibilité, couverture et organisation          | ✅ résolu (code, sans suppression) → voir `DONE.md`, attente feu vert commit |
| TICKET-002| State_Cache jamais mis à jour entre les tours                  | ✅ résolu (code) → voir `DONE.md`, attente feu vert commit |
| TICKET-003| Supprimer les modules engine dépréciés (post-Pilier 1)        | ouvert    |
| TICKET-004| Réviser le doc d'upgrade : §5.3 Étape 3 (abstraction Qt/paths) | ✅ clos → voir `DONE.md` |
| TICKET-005| Finir l'injection de chemins (`data_dir`) du Pilier 1                | ✅ clos (absorbé) → voir `DONE.md` |
| TICKET-006| Chronicler : `chronicler_update` ignoré par `_apply_event`     | ouvert    |

---

## TICKET-003 — Supprimer les modules engine dépréciés (post-Pilier 1)

**Contexte :** Pilier 1 (étape B1) a extrait le moteur dans le package `axiom/`. Les anciens
modules ont été copiés, et tous les imports (app + tests + debug) basculés vers `axiom.*`.
Les anciennes copies ne sont donc plus importées nulle part, mais **conservées volontairement**
pour validation. Marqueurs : `core/DEPRECATED.md`, `database/DEPRECATED.md`, `llm_engine/DEPRECATED.md`.

**Fichiers à supprimer (après confirmation) :**
- `core/` : `arbitrator.py`, `chronicler.py`, `rules_engine.py`, `time_system.py`, `config.py`, `paths.py`, `logger.py`, `localization.py`
- `database/` : `event_sourcing.py`, `checkpoint.py`, `modifier_processor.py`, `schema.py`, `presets.py`
- `llm_engine/` : `base.py`, `prompt_builder.py`, `vector_memory.py`, `universal_client.py`, `gemini_client.py`, `ollama_client.py`
- `workers/db_helpers.py`
- (+ les 3 fichiers `DEPRECATED.md` une fois la suppression faite)

**Conditions de suppression (toutes requises) :**
1. La nouvelle solution `axiom/` est au moins équivalente à l'ancienne (parité fonctionnelle).
2. L'app démarre et tourne parfaitement (run réel, pas seulement imports).
3. Aucune perte de fonctionnalité constatée.
4. Suite de tests verte sur le périmètre engine (hors échecs pré-existants déjà identifiés :
   pytest-qt absent, segfault torch+Qt sur run complet, test_persona_global, 6 tests test_phase6
   `_sync_current_form` inexistant).

**Priorité :** moyenne — à faire une fois les étapes 3-4 du Pilier 1 terminées et l'app éprouvée.

---

## TICKET-006 — Chronicler : `chronicler_update` ignoré par `_apply_event`

**Contexte :** Découvert en traitant TICKET-002. Le Chronicler (simulation du monde)
écrit ses changements de stats via `EventSourcer.append_event(..., "chronicler_update", ...)`
avec un payload `{entity_id, stat_key, delta|value}` (`axiom/chronicler.py:198-218`).
Or `EventSourcer._apply_event` ne gère que `entity_create` / `stat_change` / `stat_set` :
les events `chronicler_update` sont donc **silencieusement ignorés** et ne matérialisent
jamais dans `State_Cache`, **même sur `rebuild_state_cache`**. Les changements de monde
du Chronicler n'ont donc aucun effet sur les stats réelles.

**Ce qui serait à faire (à valider) :**
- Soit faire émettre au Chronicler des `stat_change`/`stat_set` standards (en gardant
  une trace « chronicler » dans le payload, ex. `source: "chronicler"`),
- Soit ajouter `chronicler_update` à la liste traitée par `_apply_event`.
- Vérifier qu'aucun autre `event_type` porteur de stats n'est dans le même cas.

**Priorité :** à confirmer — potentiellement haute (perte de fonctionnalité Chronicler),
mais vérifier d'abord si c'était intentionnel (events purement narratifs ?).

---

## TICKET-001 — Rework tests : lisibilité, couverture et organisation

**Contexte :** Audit A1-1.10. Les `debug/test_*.py` sont conservés mais hors portée pytest. Les `tests/` couvrent bien l'engine mais manquent d'explicité (noms, docstrings, output verbose) et certains cas utiles existent en double (debug/ vs tests/).

**Ce qui serait à faire :**
- Rendre les noms de tests auto-documentants (ce qu'on teste, sous quelle condition, résultat attendu)
- Migrer les `debug/test_*.py` de type `unittest.TestCase` vers `tests/` une fois complétés/nettoyés, supprimer les doublons debug/
- S'assurer que tout ce qui sera ajouté (Piliers 1–7) a une couverture pytest dès le départ
- Évaluer pytest `--verbose` / `--tb=short` comme standard de run pour lisibilité output

**Priorité :** basse — à faire après stabilisation Phase A/B.
