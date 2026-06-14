---
name: project-beta-launch
description: Cap projet décidé le 2026-06-12 — recruter des bêta-testeurs (app + lib), préparation dans TICKET-062
metadata:
  type: project
---

**Décision utilisateur (2026-06-12) : le projet part en recrutement de bêta-testeurs** (app GUI
+ lib `axiomai-engine`, voire petits collaborateurs). Toute la préparation est spécifiée dans
**`maintenance/PENDING.md` → TICKET-062** : univers par défaut fondé sur **Myria** (fiction perso
de l'utilisateur — **item 1 FAIT le 2026-06-12** : univers créé `universes/Myria/` + installation
au 1ᵉʳ lancement câblée via `core/bundled_universes.py`, reste relecture canon + commit ; ⚠ sur
SA machine le Hub montrait 2 « Myria », vieux db de test supprimé par lui le 2026-06-12),
clés Fireworks.ai embarquées temporairement — **item 2 FAIT le 2026-06-12** : 4 clés AXIOMAI-0..3
(2×6 $ + 2×1 $, ⏰ **expirent le 2026-06-30** → retirer/renouveler le pool ensuite) obfusquées
dans `core/builtin_keys.py`, rotation auto, plafond modèles pas chers, bouton « Parcourir » les
modèles, 1ᵉʳ lancement zéro-config → fireworks/`gpt-oss-120b` (l'ancien défaut deepseek-v3p1 est
mort chez Fireworks). **Item 4 (outil de diagnostic) FAIT — CLI + GUI Aide→Diagnostic.**
**Items 1, 2, 4 VALIDÉS GUI par l'utilisateur le 2026-06-13.** TICKET-050 (fail-fast 429) FAIT
et **CI GitHub Actions FAITE** (`.github/workflows/tests.yml`, 2 lots, matrice 3.11/3.12 — reste
à confirmer verte au 1ᵉʳ push). **Restent : finir le support Windows + nouvelles captures + GIF**
(les assets du README datent).

**Support Windows — QA sur VRAIE machine le 2026-06-14** (Win 11, Python 3.13) : l'audit statique
du 2026-06-13 disait « moteur déjà Windows-safe » → **FAUX**. La 1ʳᵉ exécution réelle a révélé une
**classe entière de bugs** : `with sqlite3.connect(...) as conn:` **ne ferme pas la connexion**
(gère seulement la transaction) → sous Windows le handle ouvert + le `-shm` WAL mappé
**verrouillent le `.db`** → `os.replace`/`unlink` lèvent `PermissionError [WinError 32]` (invisible
sous Linux : POSIX autorise rename/unlink d'un fichier ouvert). C'était la cause du crash rapporté
au démarrage (`universe.db.tmp -> universe.db`). **Tout corrigé** : `get_connection` renvoie une
`_ClosingConnection` (ferme en sortie de `with`, fix d'un point pour ~75 sites), migrations en
`closing()`, `axiom/fsutil.py` (retry borné anti-verrou transitoire Defender/indexeur), bascules
atomiques en `replace_with_retry`. Bonus Windows trouvés/corrigés : frontmatter lore CRLF ignoré
(`compile.py`), chemins de diff en `\` (`library.py`), suppression hardcore qui échouait à tort
(`workers/hardcore_worker.py`). **Suite 753✅/2 skip sous Windows** (cf.
`maintenance/TICKET-062-windows-support/CHANGELOG.md`). **2ᵉ découverte → TICKET-070** : **torch ne
charge pas** (`OSError WinError 126`) car le **Microsoft Visual C++ Redistributable x64 manque** sur
la machine → embedding/mémoire sémantique HS ; l'app dégrade gracieusement (no-op + warning) mais
**il faut installer `vc_redist.x64.exe`**. Reste non testé : audio `.ogg`, images locales, `run.bat`
de bout en bout (TICKET-069).

**TICKET-066 — chemin de raisonnement VALIDÉ de bout en bout le 2026-06-12** (bloquant bêta :
gpt-oss = modèle de raisonnement → Timekeeper crashait, narration vide, « Generating »
interminable) : fix backend = floor `max_tokens=2048` + `reasoning_effort: low` + tolérance
`content` absent dans `axiom/backends/universal.py`. Vérifié en réel : streaming gpt-oss-20b
(1ᵉʳ token ~2 s) ET tour complet sur Myria via `Session` (= chemin GUI), narration streamée
identique à la finale (pas d'avalement de fence JSON). **L'échec GUI répété (« ça marche pas »
/ « la réponse n'arrive pas ») n'était PAS le backend → TICKET-068** : le 1ᵉʳ tour de chaque
session figeait ~87 s parce que le modèle d'embedding `all-MiniLM-L6-v2` faisait un HEAD réseau
vers HF Hub à chaque chargement, qui stalle sur l'IPv6 cassée de la machine (même cause que le
fix Gemini `IPv4FirstTransport`, indépendant du backend LLM). Corrigé par `local_files_only=True`
dans `axiom/memory.py::_EmbeddingSingleton` (essai offline → fallback online unique si pas
caché) : 86,7 s → 3,2 s, tour Myria 1ᵉʳ token à 3,9 s. **TICKET-066 + TICKET-068 VALIDÉS GUI le
2026-06-13** (gel disparu, narration reasoning OK). Au passage : segfault de suite préexistant
consigné en TICKET-067.

Canaux visés : SillyTavern (l'app importe leurs cartes — à mettre en avant dans le README),
r/LocalLLaMA, LinuxFr.org, itch.io, Show HN/r/Python pour la lib. Conseillé avant annonce :
TICKET-050 (fail-fast 429) + CI tests.

**CI GitHub Actions — cause du fail permanent trouvée (2026-06-14)** : le workflow `tests`
échouait à chaque push (PAS un problème de droits GitHub ni un vrai test cassé) — collection
pytest interrompue par `ImportError: libpulse.so.0` : QtMultimedia (importé par
`test_ambiance_manager.py` ET indirectement `test_vector_threading.py`) a besoin de la lib
système PulseAudio, absente des `apt-get install` du workflow. **Fix : ajout de `libpulse0`** à
`.github/workflows/tests.yml`. Le workflow `docs` lui passait déjà. En plus, **1 test local
cassé** par le commit `0e956ae` (« Fix: Information button text », `?` → `tr("information")`) :
`test_help_system.py::test_make_help_button` mis à jour. **Outil de diagnostic enrichi**
(`tools/diagnostic.py`) : `--tests` liste désormais chaque test échoué (node id + raison via
`-rfE`), le nombre de warnings, et écrit le log complet dans `tempfile.gettempdir()/axiom_diag_*.log`.
Le **GUI** (`ui/diagnostic_dialog.py`, ouvert via Aide→Diagnostic) consomme le même
`run_diagnostics`+`format_report` → il hérite automatiquement de ces infos. **Lanceur GUI
standalone ajouté** : `python -m tools.diagnostic --gui` (flag `--gui` → `_run_gui()` réutilise
`DiagnosticDialog`). **README** : section « Diagnostic / Troubleshooting » documente les 3 accès
(menu app, `--gui`, mode texte). **GUI enrichi (2026-06-14, 2ᵉ passe)** : le rapport n'affichait
que le *nombre* de warnings → ajout de 2 boutons « Voir les avertissements » / « Voir les tests
échoués » ouvrant chacun une fenêtre `_TextWindow` copiable (bouton « Tout copier »). Plomberie :
`Section` porte `warnings_text`/`failures_text` ; `_run_test_batch` retourne un `_BatchOutcome`
(capture le bloc « warnings summary » même en succès, + log complet des échecs) ; helper
`collect_artifacts()` ; worker émet un 2ᵉ signal `artifacts_ready(str,str)`. 3 clés i18n ajoutées
aux **10** langues (`diagnostic_view_warnings/_view_failures/_copy_all`) — le test
`test_localization_coverage` exige toutes les langues. ⚠ rien commité (l'utilisateur gère git).

Lié : [[project-doc-chantier]] (doc finie = prérequis rempli), [[project-engine-split-strategy]]
(PyPI 0.1.3 prêt à publier, page EN + lien doc).
