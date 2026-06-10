---
name: project-pilier2-status
description: État AxiomAI — Pilier 2 terminé+validé GUI ; TICKET-028 (GUI saves) et 029 (Studio onglet Fichiers) IMPLÉMENTÉS le 2026-06-09 (validation GUI utilisateur en attente) ; 030 (Populate) en attente de cadrage utilisateur
metadata:
  type: project
---

**Pilier 2 — Universe-as-Code : TERMINÉ et validé en GUI réelle par l'utilisateur (2026-06-09).**
Branche `dev-0`, working tree non commité (l'utilisateur gère git, cf. [[feedback-user-handles-git]]).
Source de vérité : `maintenance/B2-pilier2-universe-as-code/{TODO,CHANGELOG}.md` + `maintenance/PENDING.md`.

**Architecture en place :** univers = arbo texte (`universes/<nom>/` + cache `.axiom-cache/universe.db`),
saves = fichiers autonomes `saves/<univers>/save_<uuid>.db` (`axiom/savestore.py` : create/list/
resolve/prepare/delete/duplicate/pack/unpack ; legacy embarquées toujours jouables). Refresh de
définition **in-place** partout ; `Entities.origin` protège joueur/PNJ runtime. Studio → source
resynchronisée à chaque écriture (`axiom/library.py::sync_source_if_any`). Exports : `.axiom` v2
et `.axiomsave`. Hot reload `axiom dev`. Sauvegarde = continue (event-sourcing) ; « save
manuelle » = duplication/fork. `tests/conftest.py` isole `AXIOM_DATA_DIR`.

**UX post-Pilier 2 (demandes utilisateur 2026-06-09) :**
1. **TICKET-028 — FAIT (code) le 2026-06-09** : panneau saves dans le Setup (Exporter/Importer
   `.axiomsave`, Dupliquer, Renommer, Éditer via save_state.toml en diff `manual_edit`,
   Supprimer) ; fix latent Delete/Rename qui étaient no-op sur saves séparées ; backups
   `auto_backups/` en un seul fichier (checkpoint WAL + absorption des sidecars historiques).
   Doc : `maintenance/TICKET-028-gui-saves/`. ⚠ Validation GUI utilisateur en attente.
2. **TICKET-029 — FAIT (code) le 2026-06-09** : onglet « Fichiers » du Creator Studio
   (`ui/widgets/universe_files_tab.py`) — arbo TOML/MD éditable, save → `refresh_definition`
   + reload des vues ; .db plat → conversion en univers-dossier
   (`axiom.library.convert_flat_db_to_folder`, saves embarquées migrées, original en `.db.bak`).
   Doc : `maintenance/TICKET-029-studio-fichiers/`. ⚠ Validation GUI utilisateur en attente.
3. **TICKET-030 — FAIT (code) le 2026-06-09**, périmètre validé par l'utilisateur le même jour :
   Populate ciblé + prévisualisation du diff texte (sandbox : copie db → génération → sync arbre
   temporaire → diff vs baseline normalisée → Appliquer/Annuler) + canonisation in-game
   (Tabletop : bouton « Canoniser… » avec preview, toggle « Canon auto » silencieux OFF par
   défaut ; écrit dans l'UNIVERS puis resync la save). §7.9 (authoring LLM→texte direct) écarté.
   Doc : `maintenance/TICKET-030-populate-uac/`. ⚠ Validation GUI utilisateur en attente
   (les chemins LLM exigent une clé Gemini).
Tickets 028→031 et 033 : **VALIDÉS en GUI par l'utilisateur le 2026-06-10** → archivés dans
DONE.md (PENDING a une règle de vie : un ticket terminé quitte PENDING, index compris ; il n'y
reste que 009 différé et 017 ouvert).
5. **TICKET-033 — FAIT + validé le 2026-06-10** : compte à rebours des retries 429 dans la barre
   de statut + bouton « ✖ Annuler la génération » (annulation coopérative, registre process-wide
   dans workers/db_tasks.py, hooks on_status/cancel_event sur LLMBackend). Doc :
   `maintenance/TICKET-033-annulation-generation/`.
4. **TICKET-031 — FAIT (code) le 2026-06-10** (demande utilisateur après un Populate mort en
   429 free tier) : retry au délai suggéré par l'API + ralentisseur `llm_requests_per_minute`
   + `gemini_fallback_model` (backend Gemini, couvre tous les appels) ; Populate entités
   commité par chunk (relance = reprise). Doc : `maintenance/TICKET-031-quota-llm/`.
   ⚠ Validation utilisateur en attente (gros Populate free tier, req/min = 9).
TICKET-032 (verbosité stockée localisée) : ✅ résolu le 2026-06-10 (`canonical_verbosity` +
combo Studio en itemData canonique, migration douce des univers existants — cf. DONE.md).
Vérif ouverte : nom obtenu lors d'un import direct de carte SillyTavern (`_run_import_st`,
normalement `ST_<nom>.db`) — demander le nom exact vu par l'utilisateur.

**Migration `Populate*` → `axiom/populate.py` : FAITE le 2026-06-10** (étape
`maintenance/B3-populate-vers-engine/`) : 7 générateurs zéro Qt, LLM injectable, tâches Qt en
coquilles, CLI `axiom populate`, ligne retirée d'ARCHITECTURE.md. Le chantier Pilier 2 + son UX
est COMPLET côté code — il ne reste que les validations GUI utilisateur (028/029/030/031).

**B4 (2026-06-10) : portage moteur TERMINÉ — la table « non migré » d'ARCHITECTURE.md est VIDE.**
Portés : create_player_entity (db_helpers), regenerate_variant (axiom/regenerate.py +
Session.regenerate_variant), mini_dico (axiom/mini_dico.py), multijoueur
(axiom/multiplayer.py::ActionQueue). Workers = coquilles. `workers/chronicler_worker.py`
SUPPRIMÉ (feu vert utilisateur 2026-06-10) ; au passage, chemin de mort hardcore réparé
(référence au worker retiré + garde isRunning sur DbWorker, cf. CHANGELOG B4).

Vérif GUI optionnelle (non bloquante, l'utilisateur sait) : les 4 points de contact du portage
B4 — créer une entité joueur, bouton Régénérer, question Mini-Dico, tour multijoueur.

Hors chantier : §7.8 plugins (Pilier 6), rewind en minutes (Pilier 5 = domaine Gemini),
TICKET-009 split packaging (plus aucun prérequis de migration), TICKET-017.
Tout est désormais COMMITÉ sur `dev-0` (67c89a3, 03458ae, 210fa21 — commits du 2026-06-09/10).

**QA du 2026-06-10 + fixes (même jour)** : revue complète des features récentes → 9 tickets
(TICKET-034→042), confirmés purs bugs (zéro arbitrage d'archi) puis **tous corrigés** sur
feu vert utilisateur (étape `maintenance/QA-fixes-034-042/`, archivés dans DONE.md).
Décisions notables : id d'entité non-latin = hash déterministe (idempotence Populate) ;
conversion .db plat marque les joueurs `origin='runtime'` (hors héros compagnon) ;
export `.axiom` = définition seule (cache purgé des tables runtime) ; saves importées
re-liées à l'univers local (`definition_hash` vidé → resync au 1er lancement).
Suites vertes : 512 (non-Qt) + lot Qt/vector. Travail dans le working tree, non commité.

**QA post-merge (2026-06-10, après merge `9814896` Companion+images dans dev-0)** : merge vérifié
sain (zéro perte dev-0, config/i18n/quotas préservés, API `intents=` propagée partout côté prod,
580 tests verts). Corrigé en séance : `tests/test_engine_port_b4.py` (fake `ActionQueue` non migré
vers `intents=` → gelait pytest). Ouverts : TICKET-043 (id joueur `"player"` en dur dans
`session.py` → contexte Héros/images silencieusement vide, prio moyenne-haute), 044 (artefacts du
merge à supprimer, feu vert requis), 045 (mock 1×1 affichée sur échec backend image), 046 (i18n
contournée onglet Illustration), 047 (format SIMULTANEOUS sur action solo), 048 (images vs
fork/suppression/.axiomsave/rewind). Étape : `maintenance/QA-post-merge-companion-images/`.

**Fixes QA post-merge (2026-06-10, même jour, feu vert utilisateur)** : TICKET-043→048 tous
corrigés (étape `maintenance/QA-fixes-043-048/`, archivés dans DONE.md). Décisions actées :
id joueur résolu depuis les intents (jamais `"player"` en dur), mock image réservé au backend
`"mock"` (échec réel → None), illustrations = partie de la save (suivent duplication/suppression/
`.axiomsave`/rewind/mort hardcore, helper `paths.get_assets_dir()`), pas d'images sur le chemin
multijoueur. PENDING ne contient plus que 009 (différé) et 017 (Gemini). Travail dans le working
tree, non commité.
