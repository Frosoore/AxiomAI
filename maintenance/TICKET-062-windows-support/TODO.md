# TICKET-062 item 3 — Audit du support Windows

**Statut : audit code complet le 2026-06-13. ⚠ AUCUNE machine Windows ici → audit
STATIQUE.** Les correctifs sûrs sont appliqués ; le reste demande un test réel sous Windows.

## Méthode

Balayage de tout le repo (`axiom/` 44, `core/` 6, `ui/` 30, `workers/` 12, `tools/` 3,
`main.py`) sur les motifs qui cassent typiquement sous Windows :
encodages (`open` sans `encoding=`), chemins POSIX en dur, `subprocess`/shell, signaux/`fork`,
`tempfile`, permissions/`chmod`, verrous de fichiers (sqlite ouvert vs suppression/renommage),
noms de fichiers illégaux, audio Qt, scripts `.bat`.

## Verdict global

**La couche moteur + workers est remarquablement Windows-aware.** Rien à corriger côté code
applicatif. Constats positifs vérifiés :
- **Chemins** : `pathlib` partout, `axiom/paths.py` gère déjà `%APPDATA%`/`%LOCALAPPDATA%`
  (branche `sys.platform == "win32"`). Zéro `/tmp`, `/home` en dur.
- **Encodage** : un seul `open()` sans `encoding=` → `axiom/saves.py:234` en `"rb"` (binaire, OK).
  `.bat`/JSON/TOML lus/écrits en `utf-8` ou binaire partout ailleurs.
- **Pas de** `os.fork`, `signal.*`, `os.kill`, `os.chmod`, `os.symlink` (rien de POSIX-only).
- **Verrous sqlite** : l'idiome `with sqlite3.connect()` (qui ne **ferme pas** la connexion) est
  bien neutralisé — la connexion meurt au retour de fonction (refcount CPython) **avant** toute
  suppression/renommage. `compile.py` (`tmp_db.replace`) et `package.py`
  (`_runtime_free_cache_copy`) ferment explicitement (`conn.close()` / `closing()`) AVANT le
  `replace`/la sortie de `TemporaryDirectory`, avec checkpoint WAL → bascule atomique Windows-safe.
- **Mode hardcore** : conçu pour Windows (sonde de verrous `_find_locked_files`, flush WAL,
  `journal_mode=DELETE` pour libérer les sidecars, `OSError` sur `unlink` géré par un message
  utilisateur au lieu d'un crash).
- **Noms de fichiers** : `axiom/decompile.py::_safe_filename` remplace tout caractère hors
  `[a-zA-Z0-9-_]` par `_` → les caractères interdits Windows (`: * ? " < > |`) ne peuvent jamais
  atterrir dans un nom de fichier d'univers/lore/entité.
- **subprocess** : seul `tools/diagnostic.py` en lance un (pytest) → utilise `sys.executable`
  (pas `"python"`), pas de `shell=True`.

## Corrigé cette session (bugs Windows concrets, sûrs)

- [x] **`run.bat` : plancher Python faux** — annonçait `3.10+` alors que le repo exige **3.11**
  (`tomllib`). Un utilisateur Windows en 3.10 passait le check puis crashait à l'import.
  → check + messages passés à **3.11** (cohérent avec `run.sh`/CI).
- [x] **`run.bat` + `test.bat` : ligne de commentaire en `#`** — `#` n'est PAS un commentaire batch
  (`'#' is not recognized…`). → remplacé par `REM` (+ em-dash `—` → `-`).
- [x] **`test.bat` : emoji `🧪`** dans un `echo` (charabia sur la code page console par défaut)
  → retiré.
- [x] **`tools/diagnostic.py` : crash possible en redirection** — le rapport utilise ✅/⚠️/❌ ;
  `python -m tools.diagnostic > rapport.txt` sous Windows (stdout cp1252) lèverait
  `UnicodeEncodeError`. → garde `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`
  en tête de `main()`. (La GUI Aide→Diagnostic était déjà sûre : Qt gère l'unicode.)

## Reste — NÉCESSITE une vraie machine Windows (non corrigeable à l'aveugle)

- [ ] **Audio `.ogg`** (`ui/ambiance_manager.py`) — `QMediaPlayer` sous Windows = backend Media
  Foundation, qui **ne décode pas OGG Vorbis** sans codec tiers. Les ambiances `.mp3`/`.wav`
  marchent ; les `.ogg` resteront muettes. Sévérité **basse** (ambiance optionnelle). Piste si
  confirmé : privilégier mp3/wav pour les assets fournis, ou documenter le besoin de codecs.
- [ ] **Install des deps lourdes** : `torch`, `chromadb`, `sentence-transformers`, PySide6 sous
  Windows (wheels CPU existent ; à vérifier sur 3.11/3.12). À tester via `run.bat`.
- [ ] **Génération d'images** locale (SD WebUI/ComfyUI) : chemins/URL localhost identiques, mais
  jamais lancé sous Windows.
- [ ] **Lancement réel** : `run.bat` de bout en bout (venv, deps, `startup_check.py`, GUI),
  audio, un tour de jeu, le Studio, le diagnostic GUI.

## Vérif des dépendances pour Windows (2026-06-13)

`requirements.txt` = 8 paquets : `PySide6`, `chromadb`, `sentence-transformers`, `httpx`,
`google-genai`, `requests`, `Pillow`, `tomlkit`. **Tous cross-platform, wheels Windows
disponibles pour CPython 3.11/3.12/3.13. Aucun paquet Linux-only → aucun marqueur de plateforme
nécessaire.** `torch` (2.12 en local) arrive **en transitif** via `sentence-transformers`
(`Requires: torch`) — wheels CPU Windows OK ; `chromadb` tire `onnxruntime` + `scikit-learn`/
`scipy` (wheels Windows OK). Vérifié : tout résout/importe en local (Linux, Python 3.14.5).

**⚠ Risque réel n°1 (top recommandation avant bêta) : versions non bornées (`>=`) + pas de
borne haute Python.** `run.bat` exige `>=3.11` sans plafond. Un testeur Windows avec le **Python
le plus récent de python.org (3.14)** passerait le check, puis `pip install` pourrait échouer :
`onnxruntime`/`torch`/`PySide6` **ne publient pas toujours de wheel `cp314` Windows** → pip tente
une compilation source → échec (pas de compilateur). Pistes :
- **Recommander Python 3.11–3.13 sur Windows** (doc README + message `run.bat`) — *décision
  utilisateur, non appliqué d'office* ;
- éventuellement borner légèrement les deps avant la bêta (stabilité, mais cross-platform — hors
  périmètre Windows strict).

**Conclusion deps :** rien à corriger dans `requirements.txt` pour Windows en soi ; le seul vrai
point est la **version de Python** choisie par le testeur.

## Vérif `run.sh` (Linux — pas vérifié depuis longtemps, 2026-06-13)

Globalement **sain** : plancher Python 3.11 correct, détection venv déplacé/cassé robuste,
réinstall des deps seulement si le hash de `requirements.txt` change, `exec python3 main.py`.
- **Corrigé** : code mort retiré (fonction `check_lib()` + tableau `MISSING_LIBS` **définis mais
  jamais appelés** — vestige d'un refacto ; les checks `libxcb-cursor`/`libQt6Svg` réels sont
  inline juste après). `bash -n run.sh` et `bash -n test.sh` : syntaxe OK.
- RAS sinon : `run.sh` n'installe que `requirements.txt` (normal pour un lanceur ; les deps de
  test sont gérées par `test.sh`).

## Note

`test.bat` lance `pytest` en **un seul lot** (pas le découpage 2-lots de la CI/`run.sh`). Le
segfault TICKET-067 est lié à `triton` (paquet quasi Linux-only, généralement **absent** sous
Windows) → probablement sans objet là-bas. Laissé tel quel ; à revoir si un testeur Windows voit
le crash.
