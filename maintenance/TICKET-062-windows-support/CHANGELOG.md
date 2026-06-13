# CHANGELOG — Audit support Windows (TICKET-062 item 3)

## 2026-06-13 — audit statique + correctifs scripts

Audit de code complet (pas de machine Windows → statique). Conclusion : le moteur et les
workers sont déjà Windows-safe (pathlib, fermeture sqlite avant replace/unlink, sanitisation
des noms de fichiers, hardcore conçu pour Windows). Les seuls bugs concrets étaient dans les
lanceurs `.bat` + un risque d'encodage dans le diagnostic CLI.

### Corrigé
- `run.bat` — plancher Python `3.10+` → **`3.11+`** (check `sys.version_info` + 2 messages),
  cohérent avec `run.sh`/CI (le repo exige 3.11 pour `tomllib`).
- `run.bat`, `test.bat` — ligne de titre en `#` (invalide en batch) → `REM` ; em-dash → `-`.
- `test.bat` — emoji `🧪` retiré d'un `echo` (illisible sur la console Windows par défaut).
- `tools/diagnostic.py::main` — `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`
  pour ne pas lever `UnicodeEncodeError` sur les glyphes ✅/⚠️/❌ en stdout redirigé (cp1252).

### Vérifications
- `python -m tools.diagnostic --offline` : rapport OK, exit 0.
- `pytest tests/test_diagnostic.py tests/test_diagnostic_dialog.py` : **25 passed**.
- Pas de régression : aucune logique applicative touchée (scripts + 1 garde-fou stdout).

## 2026-06-13 (suite) — vérif requirements + run.sh

### Vérifié
- `requirements.txt` (8 paquets) : tous cross-platform, wheels Windows OK pour CPython
  3.11–3.13, aucun Linux-only → **aucun marqueur de plateforme à ajouter**. `torch` transitif
  via `sentence-transformers` (wheels CPU Windows OK). Tout résout/importe en local.
- **Risque identifié** (→ TICKET-069) : `>=` non borné + `run.bat` sans plafond Python ⇒ un
  Python 3.14 Windows peut casser l'install (pas de wheel `cp314` pour onnxruntime/torch/PySide6).

### Corrigé
- `run.sh` : code mort retiré (`check_lib()` + `MISSING_LIBS`, jamais appelés). `bash -n` OK
  sur `run.sh` et `test.sh`.

### Reste (test réel Windows requis) → suivi dans TICKET-069
Install des deps sur vraie machine (selon version de Python), audio `.ogg` (Media Foundation
ne décode pas Vorbis), génération d'images locale, lancement `run.bat` de bout en bout.
