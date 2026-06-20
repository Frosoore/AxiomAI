# TODO — Phase 4 (B-3 missions + prompt caching)

## B-3 — mission de croyance par personnage/univers ✅
- [x] `axiom/missions.py` : `Universe_Meta` (`belief_mission` défaut + `belief_missions` JSON) + helpers.
- [x] `consolidate` : section « Character memory styles » (persos présents) + mission d'univers.
- [x] Worker : charge les missions et les passe à `consolidate`.
- [x] GUI : champ « Character memory styles » onglet Metadata (→ `meta["belief_missions"]`), doc()-é.
- [x] i18n + doc ×10. Tests (`test_missions.py`).

## Prompt caching ✅ (guardé, honnête)
- [x] `GeminiClient` : cache explicite guardé (seuil de taille, mémoïsation des échecs, fallback inline).
- [x] Config `memory_prompt_cache_enabled` (off) + `build_llm_from_config` + toggle GUI Mémoire + i18n/doc.
- [x] Tests (`test_gemini_prompt_cache.py` : SDK caches mocké).

## ✅ Phase 4 (périmètre demandé) COMPLÈTE. Suite 884 ✅. Rien commité.
Restent (non demandés, plus tard) : modèles mentaux (§7.8), directives/persona (§7.9),
extraction temporelle (§7.5).
