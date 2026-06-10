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
