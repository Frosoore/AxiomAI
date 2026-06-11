# maintenance/

Ce dossier centralise le suivi de toutes les étapes de refactorisation et d'évolution du projet Axiom AI.

## Structure

Chaque étape (feature, bugfix, refacto, pilier du plan d'upgrade) reçoit son propre sous-dossier :

```
maintenance/
└── <nom-etape>/
    ├── TODO.md       — tâches à accomplir pour cette étape
    ├── CHANGELOG.md  — ce qui a été fait, commit par commit ou par session
    └── DOC.md        — documentation : objectif, décisions techniques, usage
```

## Règle

Avant de commencer à coder une étape, créer son dossier avec les trois fichiers.
Mettre à jour TODO.md et CHANGELOG.md au fil du travail.
Ne pas mélanger les étapes entre elles.

## Dev parallèle à deux

Le repo est développé **en parallèle sur deux branches** (Claude Code / Gemini CLI). La coordination
— règles de merge, fichiers chauds, qui-touche-quoi-en-ce-moment — vit dans
[`collab/`](collab/README.md). **Chaque agent lit `collab/README.md` + le `EN_COURS.md` de l'autre
dev avant de modifier `axiom/` ou un fichier partagé.**

## Étapes

| Dossier | Statut | Description |
|---------|--------|-------------|
| `A1-bugs-bloquants` | ✅ terminé | Phase A §1 — corriger les crashs latents |
| `A2-bugs-logiques` | ✅ terminé | Phase A §2 — corriger les comportements incorrects |
| `A3-optimisations` | ✅ terminé | Phase A §3 — optimisations chirurgicales (perf + logs) |
| `A4-nettoyage-code-mort` | ✅ terminé | Phase A §4 — suppression code mort |
| `A5-hotfix-import-circulaire` | ✅ terminé | Hotfix — cycle d'import introduit par A3.4 (démarrage cassé) |
| `B1-pilier1-engine-headless` | ✅ terminé (packaging différé → TICKET-009) | Phase B §5 — Pilier 1 : moteur extrait dans `axiom/` (zéro Qt). Étapes 1 (copie) ✅, 2 (bascule app+tests) ✅, 3 (paths/config) absorbée→TICKET-004, 4 (API `Session`/`Universe`) ✅. Plan révisé §5.3-bis : 5 (injection chemins) ✅, 6 (parité `Session`) ✅, 7 (worker = coquille threading) ✅ + **validé run réel GUI**, 8 (CLI `axiom play`) ✅. Bugs résolus en chemin : TICKET-007 (Gemini), TICKET-008 (segfault torch+Qt). Anciens modules dépréciés supprimés (TICKET-003 ✅). **Objectif fonctionnel atteint** (moteur pilotable hors Qt, GUI=CLI). **Split physique total + `pip install`** : reporté à **après migration de TOUTES les features** dans l'engine + reprise solo du repo → TICKET-009 ⏸ (on reste mono-repo avec séparation logique `axiom/` d'ici là). |
| `B2-pilier2-universe-as-code` | ✅ code terminé — ⚠ validation GUI réelle en attente | Phase B §7 — Pilier 2 : Universe-as-Code **complet**. Univers = arbo texte TOML/MD versionnable, `.db` = cache compilé, saves = fichiers séparés. Compiler/decompiler/packaging (.axiom v2 + compat v1) + CLI complet (`compile`/`decompile`/`pack`/`import`/`dev`/`play`/`save-*`) ; éditeur de saves ; **Phase 7** : hot reload `axiom dev` (§7.7), export `.db`→`.axiom`, découverte Hub (db plat + dossiers), worker import/export en coquille fine ; **Phase 8 (2026-06-09)** : **§7.6 saves séparées** (`axiom/savestore.py`, saves autonomes sous `saves/<univers>/`, legacy embarquées toujours jouables, patch d'univers répercuté sans casser les parties), **saves exportables** (`.axiomsave`, `save-pack`/`save-unpack`), GUI branché (setup/tabletop/hub/hardcore), **TICKET-027** (Studio → source resynchronisée), `Entities.origin` (le hot reload ne touche jamais le joueur), TICKET-026 clos (résilient confirmé). Tests : 33/33 fichiers verts + smokes réels. **Reste hors pilier** : migration `Populate*` (chantier authoring), §7.8 plugins (Pilier 6), rewind en minutes (Pilier 5) ; ⚠ parcours GUI réel à valider par l'utilisateur. |
| `B3-populate-vers-engine` | ✅ terminé | Migration de l'authoring LLM (`Populate*` ×7, carte incluse) de `workers/db_tasks.py` vers `axiom/populate.py` (zéro Qt, LLM injectable). Tâches Qt = coquilles fines, sandbox de preview branchée moteur, CLI `axiom populate`. Ligne « non migré » retirée d'ARCHITECTURE.md. Tickets UX livrés en chemin (2026-06-09/10) : TICKET-028 (GUI saves), 029 (Studio onglet Fichiers + conversion .db plat), 030 (Populate ciblé + diff + canonisation in-game), 031 (résilience quotas 429) — détails dans `TICKET-02x/03x-*/` et `PENDING.md`. ⚠ Validations GUI utilisateur en attente. |
| `B4-fin-portage-moteur` | ✅ terminé | Fin du portage moteur : la table « non migré » d'ARCHITECTURE.md est **vide**. Portés vers `axiom/` (zéro Qt) : création entité joueur (`db_helpers.create_player_entity`, fix au passage d'un corps dupliqué + NameError latent), régénération de variante (`axiom/regenerate.py` + `Session.regenerate_variant`), Mini-Dico (`axiom/mini_dico.py`), file multijoueur (`axiom/multiplayer.py::ActionQueue`). Workers/`core` = coquilles thread+signaux, API GUI inchangée. `chronicler_worker.py` mort (jamais instancié) — suppression sur feu vert utilisateur. Le TICKET-009 (split packaging) n'a plus de prérequis de migration. |
| `pilier5_temps_causal` | ✅ terminé (revu) | Phase B §6 — Pilier 5 : Le temps comme substrat causal. Review du 2026-06-07 → 7 correctifs appliqués (Time Model câblé, Timekeeper désactivable, Chronicler en minutes in-game, ligne Timeline unique, scaffolding nettoyé, tests temps causal, renumérotation). Détail : `PENDING.md`/`DONE.md` (TICKET-015→022). Reste TICKET-017 (`major_event_description`). |
| `QA-fixes-034-042` | ✅ terminé | QA complète des features récentes (2026-06-10) puis correction en lot des 9 tickets ouverts (TICKET-034→042, archivés dans `DONE.md`) : fork_save complet, Populate idempotent + noms non-latins, saves importées re-liées, conversion sans fuite du joueur, connexions sqlite fermées, export `.axiom` définition seule, garde canonisation, annulation des tâches en file, cache config, i18n, nettoyages. +8 tests. Suites vertes (512 + Qt/vector). |
| `rework-companion` | ✅ terminé | Rework intégral du mode Companion (enrichissement du contexte du LLM Héros, clarté narrative). |
| `upgrade-companion-mode` | ✅ terminé | Améliorations du mode Compagnon (richesse du contexte du Héros et de l'historique narratif). |
| `feature-image-generation` | ✅ terminé | Système de génération d'images contextuelle (APIs Stable Diffusion / ComfyUI). |
| `QA-post-merge-companion-images` | ✅ terminé | QA post-merge du 2026-06-10 (`9814896` Companion+images dans dev-0) : merge sain, 580 tests verts ; 1 test gelant pytest corrigé (`test_engine_port_b4`, fake non migré vers `intents=`) ; 6 tickets ouverts (TICKET-043→048, dont l'id joueur en dur dans `session.py`). |
| `feature-packaging-pip` | ✅ terminé | Moteur pip-installable **sans quitter le mono-repo** (TICKET-009 clos en version légère, 2026-06-10) : `pyproject.toml` racine (package `axiomai-engine`, n'emballe QUE `axiom/`, commande console `axiom`, version dynamique `axiom.__version__`), objet `axiom.help` (guide REPL), utilitaire `export_engine.py` (clone PyPI-ready + bump version + garde anti-import app + `--build`). Vérifié : wheel propre installée dans un venv vierge, 15 tests, suites vertes (548 + 55 Qt/vector). |
| `QA-fixes-043-048` | ✅ terminé | Correction en lot des 6 tickets QA post-merge (2026-06-10, archivés dans `DONE.md`) : id joueur résolu depuis les intents (plus de `"player"` en dur), artefacts du merge supprimés, échec backend image → None (plus de mock 1×1), onglet Illustration sous i18n standard, format historique solo corrigé, cycle de vie des illustrations intégré aux saves (duplication/suppression/`.axiomsave`/rewind/mort hardcore, `paths.get_assets_dir()`). +8 tests, suites vertes. |
| `fix-json-fence-streaming` | ✅ terminé | Le chat masquait les blocs d'état JSON `~~~json` mais pas ```` ```json ```` (style fréquent des modèles) → JSON visible en live (2026-06-10). Filtre de streaming étendu aux deux fences, +3 tests. |
| `image-backends-locaux` | ✅ code terminé — ⚠ test réel après redémarrage reForge | Fiabilisation SD WebUI/ComfyUI (2026-06-10) : cause racine = reForge lancé sans `--api` (corrigé en permanence dans son `webui-user.sh`) ; timeout configurable `image_timeout` (défaut 180 s, le 30 s en dur tuait toute machine lente), polling ComfyUI borné pareil, 404 → message « lancé sans --api » (vérifié en réel), champ « Délai max par image » dans l'onglet Illustration. +4 tests. **2026-06-11** : workflow ComfyUI par défaut invalide corrigé (erreurs réelles utilisateur) — checkpoint en dur remplacé par le 1ᵉʳ installé via `/object_info`, entrée VAEDecode `latent_image`→`samples`, rejet 400 → warning détaillé. +3 tests. |
| `QA-post-merge-pip-images` | ✅ terminé | QA du merge `d77db2b` (2026-06-11, packaging pip × génération d'images, résolu par l'autre dev) : **merge sain** — conflits doc/mémoire seuls et bien résolus, zéro perte de code, zéro conflit sémantique (deps pyproject OK, zéro Qt OK), 632 tests verts (15 contrat + 561 + 56 Qt/vector). 2 tickets ouverts puis corrigés dans la foulée sur feu vert : TICKET-052 (`requests` ajouté à requirements.txt) et TICKET-049 (`compile.py` compatible 3.11+, **version minimale Python harmonisée à 3.11** : run.sh 3.10→3.11, pyproject/README déjà bons — plancher réel = `tomllib`). TICKET-051 aussi corrigé sur feu vert (13 fichiers de données perso untrackés — suppression stagée, commit utilisateur — + `.gitignore` : `/saves/`, `/assets/*/`). Aucun ticket restant de cette QA. |
| `licence-attribution-pypi-links` | ✅ terminé — ⚠ accord de Frosoore requis avant push | Licence (2026-06-11) : passage GPL v3 fait puis **annulé** (malentendu utilisateur sur l'en-tête FSF clarifié) → le projet **reste AGPL-3.0-or-later**. Acquis : **obligation de citation** via `NOTICE` (terme additionnel AGPLv3 §7(b) : toute redistribution préserve « Based on Axiom AI … by 17h59 and Frosoore ») + **liens PyPI** (`[project.urls]` → repo GitHub, la lib était introuvable). Propagé : pyproject (`license-files` = LICENSE+NOTICE), README, export_engine, test packaging. Wheel validée : `License-Expression: AGPL-3.0-or-later` + 3 Project-URL. Republier sur PyPI. |
| `feature-image-backend-gemini` | ✅ code terminé — ⚠ validation GUI réelle en attente | Backend d'images `gemini` (2026-06-10) : génération des illustrations via l'API Gemini (modèle `image_gemini_model`, défaut `gemini-2.5-flash-image`) avec la clé déjà configurée pour le texte — la feature devient utilisable sans SD WebUI/ComfyUI local. Réutilise la résilience quota (TICKET-031) et l'annulation (TICKET-033) ; ratio d'aspect dérivé de largeur/hauteur ; échec → None (TICKET-045). UI : choix « Google Gemini (cloud) » + champ modèle dans l'onglet Illustration. +7 tests. Au passage : TICKET-049 ouvert (compile.py cassé sous Python ≤ 3.12, 21 tests rouges préexistants). |
