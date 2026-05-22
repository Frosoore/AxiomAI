# A1 — Changelog

## 2026-05-22
- Création de l'étape. TODO dérivé de §1 du doc d'upgrade.
- **1.1** `ui/tabletop_view.py` : `ChroniclerEngine` instancié avec ses 4 args (llm, EventSourcer, db_path, trigger_interval=cfg.chronicler_interval). Découvert au passage que l'appel à `ChroniclerWorker` était aussi cassé (passait `self._llm` en position `save_id`) — corrigé : le worker prend `(chronicler, save_id, turn_id)`, le llm vit dans l'engine. Import `EventSourcer` ajouté.
- **1.2** `ui/tabletop_view.py:733` : `rewind_to_checkpoint` → `execute_rewind` (méthode réelle de DbWorker).
- **1.3** `ui/main_window.py` : retrait du `removeWidget(findChild(QWidget))` aveugle dans `_show_settings`. `_setup_volume_slider()` retire déjà proprement `_volume_container`.
- **1.6** `workers/db_worker.py` : suppression du `DELETE FROM Entity_Stats;` redondant — la cascade FK (schema.py:40, ON DELETE CASCADE) le fait via `DELETE FROM Entities`, avec `PRAGMA foreign_keys=ON`.
- **1.9** `ui/widgets/map_editor.py:98,118` : affichage `"{distance}m"` → `"{distance} km"` (le schéma stocke distance_km).
- **1.7** déjà présent (`core/localization.py:2243`) — le doc était obsolète. Aucune action.
- **1.8** déjà résolu — une seule définition de `CreatePlayerEntityTask`. Aucune action.
- **1.4 / 1.5** non traités : explicitement liés au Pilier 5 (temps causal, Phase B). Laissés en l'état fonctionnel actuel.
- Tous les fichiers modifiés passent `py_compile`. Suite pytest non exécutée (venv torch/chromadb non installé).
- **1.10** Audité : 8 fichiers dans `debug/test_*.py`. **Décision : conservation intégrale.**
  - Scripts de debug purs (`test_rules_logic.py`, `test_translations.py`, `test_audio_crossfade.py`, `test_populate.py`) : outils de diagnostic manuel — valeur intrinsèque pour déboguer sans UI.
  - `unittest.TestCase` non ramassés par pytest (`test_db_logic.py`, `test_audio_logic.py`, `test_llm_logic.py`, `test_populate_async.py`) : couverts partiellement par `tests/`, mais suppression jugée contre-productive (debug futur, filets de sécurité manuels).
