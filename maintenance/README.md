# maintenance/

Ce dossier centralise le suivi de toutes les étapes de refactorisation et d'évolution du projet Axiom AI.

## Structure

Chaque étape (feature, bugfix, refacto, pilier du plan d'upgrade) reçoit son propre sous-dossier :

```
maintenance/
└── <groupe>/
    └── <nom-etape>/
        ├── TODO.md       — tâches à accomplir pour cette étape
        ├── CHANGELOG.md  — ce qui a été fait, commit par commit ou par session
        └── DOC.md        — documentation : objectif, décisions techniques, usage
```

Depuis le 2026-06-20, les étapes sont **regroupées par thème** (voir « Organisation » ci-dessous)
pour réduire le nombre de dossiers visibles à la racine. Le détail complet de chaque étape vit dans
son propre `CHANGELOG.md`/`DOC.md` ; le tableau ci-dessous n'est qu'un **index condensé**.

## Règle

Avant de commencer à coder une étape, créer son dossier (dans le bon groupe) avec les trois fichiers.
Mettre à jour TODO.md et CHANGELOG.md au fil du travail. Ne pas mélanger les étapes entre elles.

## Dev parallèle à deux

Le repo est développé **en parallèle sur deux branches** (Claude Code / Gemini CLI). La coordination
— règles de merge, fichiers chauds, qui-touche-quoi-en-ce-moment — vit dans
[`collab/`](collab/README.md). **Chaque agent lit `collab/README.md` + le `EN_COURS.md` de l'autre
dev avant de modifier `axiom/` ou un fichier partagé.**

## Organisation (groupes de dossiers)

| Groupe | Contenu |
|--------|---------|
| `phase-A/` | Phase A du plan d'upgrade : bugs bloquants/logiques, optimisations, code mort, hotfix import |
| `piliers/` | Piliers d'architecture B1–B4 (moteur headless, Universe-as-Code, portage) + Pilier 5 (temps causal) |
| `hindsight/` | Chantier mémoire moteur inspiré de Hindsight (recherche, faits, croyances, modèles mentaux, QA, lore sémantique) |
| `i18n-doc/` | Rework i18n + passage du moteur/CLI en anglais + doc Sphinx + doc intégrée à l'app |
| `beta-launch/` | Préparation bêta publique (univers par défaut, clés Fireworks, Windows, diagnostic, CI) |
| `images/` | Génération d'illustrations (SD/ComfyUI, backend Gemini, fiabilisation locale) |
| `companion/` | Mode Compagnon (rework + enrichissement du contexte) |
| `qa/` | Lots de QA post-merge / post-feature (hors Hindsight) |
| `audits/` | Audits qualité/perf moteur + app/CLI |
| `tickets/` | Tickets numérotés isolés (rework tests, state cache, saves, quotas, etc.) |
| `features/` | Features et fixes autonomes (prompts, édition de messages, wallpaper, providers cloud, packaging pip, licence…) |
| `site/` | Site vitrine / blog / page Dev updates |
| `collab/` | Coordination du dev parallèle (rulebook + EN_COURS.md par dev) — **reste à la racine** |

Statut global : **tout est ✅ terminé sauf** `features/fix-json-leak-and-image-prompt` (🔄 en cours),
`i18n-doc/TICKET-057-*` (🔄 doc intégrée à enrichir), `hindsight/hindsight-mining` (📋 doc de cadrage,
sans code). Tickets ouverts/différés : voir `PENDING.md` ; tickets clos : `DONE.md`.

## Étapes (index condensé)

### phase-A/
| Sous-dossier | Statut | Description |
|--------------|--------|-------------|
| `A1-bugs-bloquants` | ✅ | Corriger les crashs latents |
| `A2-bugs-logiques` | ✅ | Corriger les comportements incorrects |
| `A3-optimisations` | ✅ | Optimisations chirurgicales (perf + logs) |
| `A4-nettoyage-code-mort` | ✅ | Suppression de code mort |
| `A5-hotfix-import-circulaire` | ✅ | Hotfix cycle d'import introduit par A3.4 (démarrage cassé) |

### piliers/
| Sous-dossier | Statut | Description |
|--------------|--------|-------------|
| `B1-pilier1-engine-headless` | ✅ | Pilier 1 — moteur extrait dans `axiom/` (zéro Qt), pilotable hors GUI, CLI `axiom play`. Packaging pip différé → TICKET-009 (clos depuis, voir `features/feature-packaging-pip`) |
| `B2-pilier2-universe-as-code` | ✅ (validé GUI 2026-06-13) | Pilier 2 — univers = arbo texte TOML/MD versionnable, `.db` = cache, saves séparées (`.axiomsave`), hot reload `axiom dev`, CLI complet, éditeur de saves |
| `B3-populate-vers-engine` | ✅ | Migration de l'authoring LLM (`Populate*`) vers `axiom/populate.py` (zéro Qt), CLI `axiom populate` ; tickets UX 028→031 livrés en chemin |
| `B4-fin-portage-moteur` | ✅ | Fin du portage : création joueur, régénération de variante, Mini-Dico, file multijoueur portés vers `axiom/` ; workers = coquilles fines |
| `pilier5_temps_causal` | ✅ (revu) | Pilier 5 — le temps comme substrat causal (Time Model, Timekeeper, Chronicler en minutes, Timeline) ; review 2026-06-07 (7 correctifs). Reste TICKET-017 |

### hindsight/
| Sous-dossier | Statut | Description |
|--------------|--------|-------------|
| `hindsight-mining` | 📋 cadrage (no code) | Doc de handoff : miner algorithmes + modèle de connaissance de Hindsight, refonte mémoire moteur en 2 modes (Léger/Vivant) |
| `hindsight-phase1-recherche` | ✅ | Phase 1 — recherche hybride (scoring modulé + BM25 + RRF + cross-encoder optionnel + focus boost) |
| `hindsight-phase2-faits` | ✅ | Phase 2 — deux modes + faits LLM (table `Facts`, `factextract`, injection arbitrator, worker, onglet GUI Mémoire) |
| `hindsight-phase3-croyances` | ✅ | Phase 3 — croyances/observations (table `Observations`, consolidateur LLM, injection hiérarchique, export) |
| `hindsight-phase4-raffinements` | ✅ | Phase 4 — missions de croyance par perso/univers (B-3) + prompt caching Gemini (opt-in/fallback) |
| `qa-hindsight-2026-06-19` | ✅ | QA Hindsight : TICKET-077→081 (consolidation bornée, cache BM25, lectures réduites, alignement fait↔id, Trend déterministe + vue GUI mémoire) |
| `hindsight-followups-073-076` | ✅ | TICKET-073 (focus persos), 074 (rewind modifiers), 075 (rewind events programmés), 076 (résidu legacy) |
| `ticket-072-lore-semantic` | ✅ | TICKET-072 — Lore Book en recherche sémantique + link expansion |
| `hindsight-mental-models` | ✅ | TICKET-082 (§7.8) — modèles mentaux (`axiom/mental_models.py` + `reflect.py`), toggle GUI, onglet browser |

### i18n-doc/
| Sous-dossier | Statut | Description |
|--------------|--------|-------------|
| `TICKET-053-i18n-rework` | ✅ (relocalisé par 054) | Rework i18n : traductions sorties du code vers TOML par langue, 10 langues complètes |
| `TICKET-054-i18n-engine-gui-split` | ✅ (validé GUI) | Le moteur ne traduit plus : tout l'i18n migré dans `core/localization.py` + `core/locales/` |
| `TICKET-055-cli-english` | ✅ | CLI `axiom` (publié dans le wheel) passé FR→EN |
| `TICKET-056-engine-english` | ✅ | Messages user-facing du moteur (exceptions, events `axiom dev`, statuts) FR→EN |
| `TICKET-057-doc-integree` | 🔄 contenu à enrichir | Doc intégrée à l'app GUI (tooltips, « explique cette page » F1, quick tour, annuaire) — structure validée, contenu trop succinct |
| `TICKET-057-enrichissement` | 🔄 passe 1 faite | Enrichissement de la doc intégrée (découpage Studio par onglet + couche de détails riches) |
| `TICKET-058-doc-sphinx` | ✅ (activer Pages) | Site de doc public de la lib (Sphinx, EN+FR, GitHub Pages) |
| `TICKET-060-help-english` | ✅ | `axiom.help` (guide REPL publié dans le wheel) FR→EN |

### beta-launch/
| Sous-dossier | Statut | Description |
|--------------|--------|-------------|
| `TICKET-062-univers-par-defaut` | ✅ (validé GUI) | Univers Myria embarqué + câblage 1ᵉʳ lancement (`core/bundled_universes.py`) |
| `TICKET-062-clefs-fireworks` | ✅ (validé GUI, ⏰ clés exp. 2026-06-30) | Onboarding zéro-config : clés Fireworks obfusquées + rotation + kill-switch |
| `TICKET-062-windows-support` | ✅ audit code | Audit/correctifs Windows-safe (run.bat, sqlite fermées, sanitisation) ; reste test machine réelle (TICKET-069) |
| `TICKET-062-outil-diagnostic` | ✅ (validé GUI) | Outil de diagnostic CLI + GUI (Aide → Diagnostic) |
| `beta-diagnostic-venv-i18n` | ✅ | Diagnostic externe ré-exécuté dans le `.venv` + i18n du rapport (57 clés ×10) |
| `myria-rules` | ✅ | Règles déterministes pour l'univers vitrine Myria (4 règles) |
| `CI-github-actions` | ✅ | CI GitHub Actions (`.github/workflows/tests.yml`, 2 lots, matrice 3.11/3.12) |

### images/
| Sous-dossier | Statut | Description |
|--------------|--------|-------------|
| `feature-image-generation` | ✅ | Génération d'images contextuelle (APIs Stable Diffusion / ComfyUI) |
| `feature-image-backend-gemini` | ✅ (validé GUI) | Backend d'images `gemini` (clé texte réutilisée, utilisable sans GPU local) |
| `image-backends-locaux` | ✅ (testé reForge) | Fiabilisation SD WebUI/ComfyUI (timeout configurable, workflow par défaut corrigé) |

### companion/
| Sous-dossier | Statut | Description |
|--------------|--------|-------------|
| `rework-companion` | ✅ | Rework intégral du mode Companion (contexte du LLM Héros, clarté narrative) |
| `upgrade-companion-mode` | ✅ | Améliorations du mode Compagnon (richesse contexte Héros + historique) |

### qa/
| Sous-dossier | Statut | Description |
|--------------|--------|-------------|
| `QA-fixes-034-042` | ✅ | QA des features récentes + correction en lot TICKET-034→042 |
| `QA-fixes-043-048` | ✅ | Correction en lot des 6 tickets QA post-merge TICKET-043→048 |
| `QA-post-merge-companion-images` | ✅ | QA post-merge Companion+images (TICKET-043→048 ouverts) |
| `QA-post-merge-pip-images` | ✅ | QA du merge packaging pip × images (merge sain, 632 tests verts) |
| `QA-test-connexion-gemini` | ✅ (validé GUI) | QA « Test Connection » Gemini → fix `IPv4FirstTransport` (IPv6 cassée vers Google) |
| `QA-ambiance-images-2026-06-13` | ✅ | QA ambiance sonore + images |
| `qa-fs-univers-saves-2026-06-21` | ✅ | QA e2e fichiers/univers/saves : fix `fired_turn_id` perdu (extract/fork) + test de garde anti-dérive schéma↔copie ; findings TICKET-087→090 |

### audits/
| Sous-dossier | Statut | Description |
|--------------|--------|-------------|
| `audit-moteur-2026-06-14` | ✅ | Audit qualité/optim. moteur `axiom/` (3 bugs, 3 archi/scaling, 5 micro-opt) |
| `audit-moteur-2-2026-06-14` | ✅ | 2ᵉ passe d'audit moteur |
| `audit-app-cli-2026-06-14` | ✅ | Audit couche app GUI (`ui/`, `workers/`, `core/`) + CLI |

### tickets/
| Sous-dossier | Statut | Description |
|--------------|--------|-------------|
| `TICKET-001-rework-tests` | ✅ | Rework des tests |
| `TICKET-002-state-cache-sync` | ✅ | Synchronisation State_Cache |
| `TICKET-028-gui-saves` | ✅ | GUI saves |
| `TICKET-029-studio-fichiers` | ✅ | Studio onglet Fichiers + conversion .db plat |
| `TICKET-030-populate-uac` | ✅ | Populate ciblé + diff + canonisation in-game |
| `TICKET-031-quota-llm` | ✅ | Résilience quotas 429 |
| `TICKET-033-annulation-generation` | ✅ | Annulation des tâches en file |
| `TICKET-050-fail-fast-429` | ✅ | Fail-fast sur 429 |
| `TICKET-066-reasoning-models` | ✅ (validé GUI) | Modèles de raisonnement (gpt-oss) |
| `TICKET-068-embedding-offline-stall` | ✅ (validé GUI) | 1ᵉʳ tour figé ~90 s → `local_files_only=True` dans `axiom/memory.py` |

### features/
| Sous-dossier | Statut | Description |
|--------------|--------|-------------|
| `feature-basic-prompt` | ✅ | Zone « Basic Prompt » dans les paramètres (instructions personnalisées) |
| `feature-negative-prompt` | ✅ | Zone « Negative Prompt » (instructions négatives, ajoutées au system prompt) |
| `feature-custom-wallpaper` | ✅ | Fond d'écran personnalisé (styling QApplication, transparence glassmorphique) |
| `feature-edit-messages` | ✅ | Édition dynamique des messages d'historique (IA → patch payload+RAG ; joueur → rewind+regénération) |
| `feature-edit-start-date` | ✅ | Modifier la date de départ (jour/heure/minute) dans le créateur d'univers |
| `feature-cloud-text-providers` | ✅ (validé GUI) | Onglet Cloud : Gemini / Claude / Venice / Fireworks / OpenAI / OpenRouter |
| `feature-packaging-pip` | ✅ | Moteur pip-installable (`axiomai-engine`) sans quitter le mono-repo |
| `licence-attribution-pypi-links` | ✅ | AGPL-3.0 conservée + citation `NOTICE` + liens PyPI |
| `fix-entity-category-type` | ✅ | Fix : modifier type/catégorie d'une entité dans le Creator Studio |
| `fix-json-fence-streaming` | ✅ | Fix : masquer les blocs d'état JSON ` ```json ` (en plus de `~~~json`) en live |
| `fix-json-leak-and-image-prompt` | 🔄 en cours | Fix fuite JSON dans le chat + amélioration prompting images (négatifs + refresh) |

### site/
| Sous-dossier | Statut | Description |
|--------------|--------|-------------|
| `site-blog` | ✅ | Blog Markdown→HTML + RSS, stylé au thème du site |
| `site-dev-page-rework` | ✅ | Refonte de la page Dev updates |
