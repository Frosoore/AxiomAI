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

## 2026-06-14 (suite) — 4 chantiers de suivi demandés (branche `dev-win-compat`)

1. **Balayage des bugs de chemin** (même famille que le diff `\`) : **RAS**. Le code est discipliné
   — les noms d'archive zip utilisent déjà `.as_posix()` (`package.py`, `savestore.py`), les
   `split("/")` portent sur des IDs de modèle / URLs HTTP (pas des chemins), les comparaisons
   `relative_to` de `library.py` se font Path-à-Path (cohérent). Le bug de clés de diff corrigé hier
   était le seul.
2. **TICKET-071 — fin de la classe « connexion non fermée »** : 8 `with sqlite3.connect(...)` restants
   passés en `closing()` — `workers/db_worker.py` (×6 : tous read-only ou `commit()` explicite) et
   `workers/import_export_worker.py` (×2 : `commit()` aux l.247/355). **Pas que de l'hygiène** :
   `db_worker` save-univers appelle `sync_source_if_any()` (qui recompile/replace) *juste après* le
   bloc → l'ancien handle ouvert aurait verrouillé le `.db` sous Windows. Tests `db_worker`/studio OK.
3. **Visibilité torch/VC++** : `tools/diagnostic.py::_check_embedding_runtime` (nouveau) — tente
   l'import torch et, sur `OSError` (WinError 126), émet un **FAIL actionnable** pointant le VC++
   Redistributable (au lieu d'un WARN « not importable » noyé dans les deps). Vérifié en réel sur la
   machine : le rapport affiche bien le FAIL + le conseil. 25 tests diagnostic OK.
4. **Test run.bat + audio en RÉEL sur la machine** :
   - **Audio** : **aucun asset audio embarqué** dans le repo (l'ambiance lit des fichiers fournis par
     l'utilisateur). Sonde `QMediaFormat` sur cette Win 11 : **Ogg, FLAC, AAC, MP3, Wave tous
     supportés** → la crainte « Media Foundation ne décode pas OGG » **ne se vérifie pas** ici
     (codecs Win11 OK). Risque audio Windows ⇒ requalifié **quasi nul**.
   - **`run.bat`** : `debug/startup_check.py` passe (exit 0 : signaux DbWorker, schéma, imports cœur
     dont `ui.main_window`). **Lancement réel `main.py` (offscreen, timeout)** : l'app **atteint sa
     boucle d'événements sans crash** ; le log montre `WARNING: Embedding runtime not pre-loaded
     (torch unavailable)` → **la dégradation gracieuse fonctionne de bout en bout dans la vraie app**
     (warn + continue au lieu de crasher). Reste non couvert : un vrai tour de jeu GUI, génération
     d'images locale (services externes).

**Bilan** : la couche moteur **et** app est désormais Windows-safe pour le démarrage, la
compilation, les saves, le Studio et la suppression hardcore. Seul point ouvert = le VC++
Redistributable côté utilisateur (TICKET-070), bien signalé par le diagnostic.

## 2026-06-14 (suite 2) — alerte GUI « VC++ Redistributable manquant »

Demande utilisateur : auto-installer le composant manquant via `requirements.txt`, sinon le
détecter au lancement et proposer le téléchargement — **uniquement en couche GUI**.

- **Pourquoi pas `requirements.txt`** : pip n'installe que des **paquets Python** (wheels PyPI).
  Le VC++ Redistributable est un **composant système Windows** (installeur `.exe`/MSI, droits
  admin) → hors de portée de pip. (Le paquet bricolé `msvc-runtime` existe mais place les DLL de
  façon non fiable pour le chargeur de torch → écarté.)
- **Solution GUI** : **`ui/runtime_check.py` (nouveau, zéro code moteur)**.
  `embedding_runtime_status()` → `ok` / `missing_dll` / `not_installed` ;
  `maybe_warn_missing_runtime(parent)` n'agit **que** sous Windows + cas `missing_dll` + pas de
  marqueur « ne plus afficher ». Boîte `QMessageBox` (bouton **Télécharger** →
  `QDesktopServices.openUrl(https://aka.ms/vs/17/release/vc_redist.x64.exe)`, bouton **Plus tard**,
  case **ne plus me prévenir** → marqueur `%APPDATA%/AxiomAI/vcredist_warning_dismissed`). Best-effort,
  ne lève jamais (un dialogue d'aide ne doit pas casser le démarrage).
- **Branchement** : `main.py` appelle `maybe_warn_missing_runtime(window)` après `window.show()`
  (le moteur, lui, continue de dégrader en silence — séparation des couches respectée).
- **i18n** : 5 clés `vcredist_*` ajoutées aux **10 langues** (traductions réelles), couverture
  i18n re-vérifiée **554/554 ×10, OK**.
- **Tests** : `tests/test_runtime_check.py` (6, QMessageBox mocké → pas de modale bloquante) :
  no-op hors Windows / runtime OK / torch absent ; affichage unique + respect du marqueur ; le
  bouton Télécharger ouvre bien l'URL Microsoft. Détection vérifiée en réel (`missing_dll` sur la
  machine ; torch lui-même imprime le même conseil VC++).

## 2026-06-14 (suite 3) — QA Linux post-portage (non-régression)

Contrôle qualité sur Linux (Fedora, Python 3.14.5, torch 2.12.0+cu130) pour vérifier que la
couche compat Windows de cette branche `dev-win-compat` **ne casse rien sur POSIX**. Aucun code
modifié — vérification seule.

### Tests (machine Linux de dev)
- Suite moteur/app hors vector/Qt : **700 passed**.
- Lot vector/Qt séparé (`test_vector_memory`/`test_vector_threading`/`test_phase6`/
  `test_ambiance_manager`) : **61 passed**. Total **761 passed, 0 échec** (deux lots,
  `QT_QPA_PLATFORM=offscreen`, segfault TICKET-067 contourné comme prévu).

### Revue des changements à risque sémantique sur Linux — tous sains
- **`schema.py::_ClosingConnection`** (le plus sensible, 87 sites `with get_connection()`) :
  vérifié **zéro assignation nue**, tous les sites passent par `with`. Smoke réel : la connexion
  est bien fermée après le bloc (`Cannot operate on a closed database` à la réutilisation) et
  aucun site ne la réutilise après (sinon la suite planterait). Sur Linux, seul effet = handle
  libéré plus tôt → comportement inchangé.
- **`memory.py` dégradation gracieuse** : sur Linux torch charge, `_disabled` reste `False`,
  `_ensure_connected` réussit → comportement strictement inchangé (la dégradation ne s'arme que
  sur exception).
- **`compile.py::_split_frontmatter`** : smoke confirme LF **et** CRLF parsent à l'identique
  (`\n` toujours traité en premier, corps préservé).
- **`library.py` `.as_posix()`** : sur Linux `as_posix()` == `str()` (séparateur déjà `/`) →
  clés de diff inchangées.
- **`fsutil.py` retry** : sur POSIX la 1ʳᵉ tentative (delay 0.0) réussit toujours → no-op, zéro
  surcoût.

### Smokes end-to-end Linux
- Compile de l'univers embarqué `universes/Myria` → OK (11 entités).
- `tools.diagnostic --offline` → exit 0, embedding model en cache, config bêta OK.
- `ui/runtime_check.py` → `status="ok"`, `maybe_warn_missing_runtime(None)` renvoie `False`
  (no-op hors Windows).
- `bash -n run.sh` → OK.

**Bilan : aucune régression Linux introduite par le portage Windows.** Seul point ouvert =
environnement Windows utilisateur (VC++ Redistributable, TICKET-070), sans impact POSIX.
