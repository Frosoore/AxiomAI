# DEPRECATED — debug/test_*.py

Audit TICKET-001 (2026-05-23). Ces scripts `debug/test_*.py` sont **hors portée
pytest** (scripts à `print` / `unittest` / interactifs lancés à la main). Leur
couverture *utile et unique* a été migrée en vraies cibles pytest dans `tests/`.
**Aucun fichier n'est supprimé ici** : la suppression suivra les mêmes règles que
TICKET-003 (parité prouvée + feu vert utilisateur).

## Migrés vers tests/ (couverture unique reprise en pytest)
| debug/                     | Couverture                                  | Remplacé par                         |
|----------------------------|---------------------------------------------|--------------------------------------|
| `test_translations.py`     | Localisation (`tr`, table de langues, `fmt_num`) | `tests/test_localization.py`     |
| `test_db_logic.py`         | Round-trip params LLM dans `Universe_Meta`  | `tests/test_universe_meta.py`        |

## Déjà couverts ailleurs dans tests/ (doublons → candidats suppression TICKET-003)
| debug/                     | Déjà couvert par                            |
|----------------------------|---------------------------------------------|
| `test_rules_logic.py`      | `tests/test_rules_engine.py` (script `print`, pas d'assert) |
| `test_populate.py`         | `tests/test_prompt_builder.py::TestBuildPopulatePrompt` (le reste = logique d'ID ré-implémentée dans le test, ne teste pas le vrai code) |
| `test_llm_logic.py`        | Teste son propre `MockLLM`, pas de code réel → valeur faible |
| `test_populate_async.py`   | Smoke `hasattr(task, 'execute')` → valeur faible |
| `test_audio_logic.py`      | `test_arbitrator_result_tag_parsing` trivial ; `test_audio_folder_structure` dépend de `assets/audio` (fragile, non porté) |

## Outils manuels (NON migrables — interactifs, à conserver tels quels)
| debug/                     | Raison                                      |
|----------------------------|---------------------------------------------|
| `test_audio_crossfade.py`  | Script interactif `sys.argv` + boucle temps réel sur QApplication ; sert au debug audio manuel, pas un test automatisable. |

> Décision suppression reportée à TICKET-003 (post-Pilier 1).
</content>
