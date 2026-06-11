# CHANGELOG — QA post-merge pip + images

## 2026-06-11 — Contrôle complet du merge d77db2b

### Contrôles effectués (tous OK)

1. **Résolutions de conflits** (`git show --remerge-diff d77db2b`) : seuls 3 fichiers en
   conflit, tous doc/mémoire (`maintenance/collab/claude/EN_COURS.md`, `memory/MEMORY.md`,
   `memory/project_pilier2_status.md`). Résolutions correctes : les infos des deux branches
   sont combinées sans perte (EN_COURS vidé + lignes « mergé » ajoutées, MEMORY/statut
   fusionnés en une ligne cohérente). Aucun marqueur de conflit résiduel.
2. **Aucune perte de code** : `git diff a03edf5 d77db2b` ne montre QUE le packaging pip
   (5 fichiers, +524) ; `git diff fbe8b6e d77db2b` ne montre QUE l'image-gen (10 fichiers,
   +589/-27). Chaque branche est intégralement préservée, diffs purement additifs.
3. **Conflits sémantiques packaging ↔ images** : `pyproject.toml` déclare bien `requests`
   et `google-genai` (utilisés par `axiom/image_generator.py` / `backends/gemini.py`) ;
   `packages = find axiom*` embarque les nouveaux modules ; contrat **zéro Qt** de `axiom/`
   respecté (grep : seules occurrences PySide6 = chaînes de texte/commentaires) ;
   `axiom/__init__.py` (lazy imports + `help`) non impacté.
4. **Tests** : contrat partagé du merge `test_engine_headless` + `test_cli_play` = 15 verts ;
   `debug/startup_check.py` = PASS ; suite complète hors Qt/vector = **561 verts** ;
   lot séparé Qt/vector (`test_vector_*`, `test_phase6`, `test_ambiance_manager`) =
   **56 verts**. Total **632 tests, 0 échec**.
5. **Revue de code** des fichiers mergés côté images (`axiom/image_generator.py`,
   `axiom/backends/gemini.py::generate_image_bytes`, `axiom/config.py`,
   `axiom/localization.py`, `ui/settings_dialog.py`, `ui/widgets/chat_display.py`
   `_JSON_FENCES`) : code additif, défensif (échec → None, messages explicites),
   couvert par les nouveaux tests (`test_image_generator`, `test_chat_buffer`,
   `test_settings_dialog`).

### Trouvailles (tickets ouverts dans PENDING.md)

- **TICKET-051** : la branche image-gen a commité des **données de jeu personnelles** :
  10 saves `saves/Myria/save_*.db` (~1,7 Mo) + 3 illustrations générées
  `assets/<uuid>/turn_1.png` (~1,2 Mo). `.gitignore` couvre `universes/` mais ni `saves/`
  ni les sous-dossiers UUID de `assets/`. Nettoyage git = à la main de l'utilisateur.
- **TICKET-052** : `requests` est importé directement par `axiom/image_generator.py` mais
  absent de `requirements.txt` (présent seulement par transitivité via `google-genai`).
  Le `pyproject.toml` le déclare correctement, lui.
- **Note ajoutée au TICKET-049** : le venv local est passé en **Python 3.14.5** → les
  21 tests `compile.py` sont verts localement, MAIS la lib publiée annonce
  `requires-python >= 3.11` : le bug reste entier pour les utilisateurs pip en 3.11/3.12.

### Doc/mémoire mises à jour

- `memory/project_test_env.md` : venv = Python 3.14.5 (plus 3.12.3), tests TICKET-049
  verts localement.
- `maintenance/README.md` : ligne d'étape ajoutée.

## 2026-06-11 (suite) — TICKET-052 corrigé sur feu vert utilisateur

- `requests>=2.31.0` ajouté à `requirements.txt` (aligné sur le pyproject du moteur).
- Ticket archivé dans `DONE.md`, retiré de `PENDING.md`. Reste ouvert : TICKET-051 (nettoyage
  git par l'utilisateur).

## 2026-06-11 (suite) — TICKET-049 corrigé + version Python minimale harmonisée à 3.11

- `axiom/compile.py` (×2) : `Path.read_text(newline="")` (3.13+ seulement) remplacé par
  `path.open("r", encoding="utf-8", newline="")` (dispo depuis toujours, même fidélité LF) →
  `axiom.compile` remarche sous Python 3.11/3.12 (lib PyPI incluse).
- **Plancher réel du projet = Python 3.11** (`tomllib`, stdlib 3.11+, utilisé par
  `compile/package/library/savestore/saves` + `workers/db_tasks`). Harmonisation :
  `pyproject.toml` (`>=3.11`) et README (badge + tableaux « 3.11+ ») étaient déjà bons ;
  `run.sh` corrigé (annonçait et vérifiait 3.10+ → 3.11+, garde `-lt 11`).
- Vérifié : `test_universe_as_code` + `test_source_preview` + `test_packaging` +
  `test_cli_play` = **66 verts**. Ticket archivé dans `DONE.md`.

## 2026-06-11 (suite) — TICKET-051 corrigé sur feu vert utilisateur

- Les 13 fichiers de données perso (10 `saves/Myria/*.db` + 3 `assets/<uuid>/turn_1.png`)
  retirés du suivi git (`git rm --cached` — fichiers conservés sur le disque, suppression
  **stagée mais non commitée**, le commit reste à l'utilisateur).
- `.gitignore` : ajout de `/saves/` et `/assets/*/` (ancrés à la racine). Vérifié par
  `git check-ignore` : les cibles sont ignorées, les captures du README (`assets/*.png` à
  plat) et les fixtures `tests/data/*.db` restent versionnées.
- Ticket archivé dans `DONE.md` → **plus aucun ticket issu de cette QA n'est ouvert**
  (PENDING = 017 + 050 seulement).
