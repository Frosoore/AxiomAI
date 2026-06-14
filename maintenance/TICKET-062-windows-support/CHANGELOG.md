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

## 2026-06-14 — QA sur VRAIE machine Windows (Win 11, Python 3.13.12)

Première exécution réelle sous Windows. L'audit statique précédent avait conclu « moteur
Windows-safe » : **c'était faux**. Cause racine d'une classe entière de bugs : **`with
sqlite3.connect(...) as conn:` ne FERME PAS la connexion** (il ne gère que la transaction ;
la connexion survit jusqu'au GC). Sous Windows le handle laissé ouvert — + le `-shm` WAL
mappé en mémoire — **verrouille le `.db`** : tout `os.replace`/`unlink` ultérieur lève
`PermissionError [WinError 32]`. Sous Linux un handle ouvert n'empêche jamais un rename/unlink
(POSIX), d'où l'invisibilité totale en CI Linux. Reproduit en 6 lignes, prouvé que `close()`
explicite résout (`os.replace` après `with`-no-close → WinError 32 ; après `close()` → OK).

### Bug rapporté (crash au démarrage) — RÉSOLU
`[WinError 32] … universe.db.tmp -> universe.db` à l'ouverture (découverte Hub → compile de
Myria). Cause : `create_universe_db()` ouvrait la base en WAL via `with sqlite3.connect()` sans
fermer → `.tmp` (+ `-shm`) encore verrouillé au moment du `replace`. **Vérifié réparé** par un
smoke réel sur l'univers Myria embarqué (compile / no-op / force-replace / refresh : zéro erreur).

### Moteur (`axiom/`) — correctifs Windows
- **`axiom/fsutil.py` (nouveau)** : `replace_with_retry` / `unlink_with_retry` — retry borné
  (~1,5 s) sur `PermissionError`, pour absorber les verrous **transitoires** réels de Windows
  (antivirus Defender, indexeur) sur un fichier fraîchement écrit. Zéro coût sous POSIX.
- **`schema.py`** : **`get_connection()` renvoie désormais une `_ClosingConnection`** — sa sortie
  de bloc `with` **ferme** la connexion (au lieu de seulement committer). Corrige d'un seul point
  les ~75 sites `with get_connection(...) as conn:` (tous vérifiés : aucun ne réutilise la
  connexion après le bloc). + `create_universe_db()` et les 13 migrations `with sqlite3.connect`
  passés en `closing()`.
- **`compile.py` / `library.py` / `savestore.py`** : bascules atomiques (`replace`) et purges de
  sidecars passées en `replace_with_retry`/`unlink_with_retry`.
- **`package.py` / `library.py`** : `TemporaryDirectory(ignore_cleanup_errors=True)` (un `-shm`
  encore mappé faisait planter le `rmtree` final sous Windows).
- **`compile.py::_split_frontmatter`** : **bug d'authoring Windows** — un `.md` de lore édité sous
  Windows (CRLF) commençait par `+++\r\n` ; le parseur n'acceptait que `+++\n` → frontmatter
  (`entry_id`, `category`, `keywords`) **silencieusement ignoré**, id retombant sur le nom de
  fichier. Rendu tolérant LF **et** CRLF (corps préservé octet pour octet).
- **`library.py::diff_source_trees`** : les clés de diff utilisaient le séparateur OS
  (`entities\bob.toml`) → l'aperçu de changements de source cassait sous Windows. Passé en
  `.as_posix()` (slashes canoniques, identiques Win/Linux).

### App (`workers/`) — bug Windows réel
- **`workers/hardcore_worker.py`** : `_flush_wal` / `_delete_save_rows` / `_count_remaining_saves`
  en `with sqlite3.connect` sans close → handle résiduel → la **sonde de verrous**
  (`_find_locked_files`) voyait le `.db` « verrouillé » et **la suppression hardcore échouait à
  tort sous Windows** (message « files are still locked »). Passés en `closing()`.

### App (`axiom/memory.py`) — dégradation gracieuse
La 2ᵉ grosse découverte : **torch ne se charge pas sur cette machine** (`OSError [WinError 126]`
sur `torch_python.dll`). Cause environnementale identifiée : **le Microsoft Visual C++
Redistributable 2015–2022 x64 n'est pas installé** (seules les variantes `_clr0400` CLR sont
présentes ; `vcruntime140.dll`/`vcruntime140_1.dll`/`msvcp140.dll` manquent). Sans ça, l'embedding
crashait **chaque tour** (arbitrator `query`/`embed_chunk` non gardés).
→ `VectorMemory` **dégrade en no-op** si le runtime d'embedding ne charge pas (`_disabled`,
`query`→[], `embed_chunk`→"", `rollback`→0) + **un seul** warning explicite pointant le VC++
Redistributable. Le jeu reste jouable (sans mémoire sémantique long terme) au lieu de crasher.

### Tests
- Suite **753 passed, 2 skipped, 0 failed** sous Windows (avant : 50 échecs au 1ᵉʳ run réel).
- Corrigés côté tests (même idiome fautif tenu **par le test** à travers un swap) : `closing()`
  dans `test_universe_as_code` (×2), `test_savestore` (convert), `test_hardcore_worker` (×2).
- `test_vector_memory` + `test_arbitrator` : fixtures `vm` corrigées — le `patch` n'entourait que
  le constructeur (paresseux) ; le vrai chargement torch arrivait plus tard, hors patch. Le faux
  embedder est désormais injecté dans `_EmbeddingSingleton._instance` → tests déterministes, sans
  torch. (La dégradation gracieuse a fait passer ~32 tests « tour » qui n'assertaient pas le RAG.)
- `test_vector_threading` : `importorskip("torch")` ne captait qu'`ImportError` → le `OSError`
  WinError 126 plantait la **collecte** du module entier. Skip élargi à `(ImportError, OSError)`.
- `test_help_system::test_make_help_button` : test périmé (commit `0e956ae` « Fix: Information
  button text » : `?`→`tr("information")`), assertion mise à jour. **Pas un bug Windows.**
- `test_bundled_universes::test_never_raises_on_unwritable_library` : **skip sous Windows**
  (`chmod(0o500)` n'y rend pas un dossier non-inscriptible — bits POSIX ignorés).

### Reste (action UTILISATEUR / environnement)
- ⚠ **Installer le Microsoft Visual C++ Redistributable x64** (vc_redist.x64.exe) : débloque torch
  → mémoire sémantique fonctionnelle + les 2 tests skippés torch passeront. **Top recommandation.**
- Toujours non testé en réel : audio `.ogg`, génération d'images locale, `run.bat` bout en bout.
