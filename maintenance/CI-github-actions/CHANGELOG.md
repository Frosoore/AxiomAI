# CHANGELOG — CI GitHub Actions (tests)

## 2026-06-13 — workflow de tests

Prérequis conseillé avant l'annonce bêta (cf. TICKET-062) : lancer la suite de
tests automatiquement à chaque push/PR, surtout en vue de contributeurs.

### `.github/workflows/tests.yml` (nouveau)
- Déclencheurs : push sur `main`, toute `pull_request`, `workflow_dispatch`.
- Matrice Python **3.11 et 3.12** (plancher repo = 3.11, tomllib).
- Qt headless : `QT_QPA_PLATFORM=offscreen` + libs système
  (`libegl1 libgl1 libxkbcommon0 libdbus-1-3`) pour importer PySide6 sans display.
- Installe `requirements.txt` + `requirements-dev.txt` (torch arrive
  transitivement via sentence-transformers).
- **Suite en 2 lots** (contourne le segfault Qt-multimédia/triton TICKET-067) :
  1. `pytest tests/ --ignore=tests/test_ambiance_manager.py`
  2. `pytest tests/test_ambiance_manager.py` (lot audio, `if: always()` pour
     tourner même si le lot 1 a échoué ; le job échoue si l'un des deux échoue).
- `concurrency` : annule les runs obsolètes sur la même ref.

### Vérifications
- YAML valide (parse OK), commandes des 2 lots correctes.
- ⚠ **Non exécutable hors GitHub** : la CI ne peut être confirmée verte qu'au
  1ᵉʳ push (runner ubuntu + Python 3.11/3.12, env différent du venv local 3.14).
  Le découpage en 2 lots est la mitigation du segfault connu ; reste à voir si
  le segfault se manifeste sur ubuntu/3.11-3.12 (possiblement absent là-bas).
- Localement : le slice « fichiers touchés cette session » = 150 verts ; lot
  audio seul vérifié à part.

### Reste
- [ ] Pousser sur GitHub et confirmer le 1ᵉʳ run vert ; ajouter un badge au
  README si OK.
