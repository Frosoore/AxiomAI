# TODO — Système de mods

> Référence : `DOC.md` (vision, garde-fous §2, feuille de route §13). Ne pas mélanger les phases.
> Chaque phase ouvrira son propre sous-dossier `maintenance/Mods/<phase>/` au moment de coder.

## Cadrage
- [x] Formaliser la vision validée en discussion → `DOC.md`
- [x] Critique indépendante (agent Opus, lecture doc + code) → `CRITIQUE.md`
- [x] Arbitrage de la critique → `ARBITRAGE.md`
- [x] Décisions utilisateur D-1 → D-9 (2026-09-26) intégrées dans `DOC.md` (§2 garde-fous, §14 registre)

## Préalable — bugs confirmés (tickets normaux, hors chantier ; décision D-1)
- [ ] TICKET-100 — rewind web/CLI sans rollback ChromaDB (+ doublons uuid)
- [ ] TICKET-101 — tour échoué/annulé : `user_input` orphelin + `turn_id` décalé
- [ ] TICKET-102 — job mémoire living web sans verrou : course avec le rewind
- [ ] TICKET-103 — `fork_save --turn` copie des events planifiés / lore de session postérieurs au fork
- [ ] TICKET-104 — `regenerate.py` : remplacement de consigne sans effet → JSON dans les variantes
- [ ] TICKET-105 — `_pending_correction` non remise à zéro au rewind
- [ ] TICKET-089 (étendu) — `_RUNTIME_TABLES` oublie aussi `Item_Instances` et `Session_Lore`

## Coordination (décision D-6)
- [ ] Formaliser avec Frosoore dans `maintenance/collab/` : propriétaire unique de `arbitrator.py`/`session.py` pendant 0b/0c/0d/0f
- [ ] Statuer sur `Multiplayer/` : fini ou gelé avant 0f

## Phase 0 — Assainir le moteur (sans mods)
- [x] 0a. Harnais « golden step » (faux LLM scripté, N tours → rewind → fork → export → comparaison)
- [x] 0b. Fin de tour unique dans `Session` (mémoire living Qt/web unifiée, auto-canonize)
- [x] 0c. Un seul rewind + registre des données de save (fin des 5 listes de tables)
- [x] 0d. Tour transactionnel + époques de session
- [x] 0e. Config ouverte (`[mods.<id>]`) + version de schéma + migrations + retrait des CHECK figés
- [x] 0f. Découpage de `process_turn` en étapes nommées

## Phase 1 — Noyau
- [x] Chargeur + manifeste `mod.toml` + registre (exclusif / chaîne / collecte) + hooks + `ModContext`
- [x] Stockage par politiques + modpack + mode sans échec + CLI `axiom mods`
- [x] Évaluer `pluggy` comme brique interne (écarté au profit d'un registre noyau plus hermétique et sécurisé)
- [x] Premier mod officiel extrait (`core.stat_dynamics`) pour valider

## Phase 2 — Features en mods officiels (✅ TERMINÉE)
- [x] `axiom.world` & `axiom.turn` (modèle de monde et pipeline du tour)
- [x] `axiom.time` & `axiom.inventory` (gestion causale du temps et des conteneurs)
- [x] `axiom.rag` & `axiom.living_memory` (mémoire sémantique vectorielle et mémoire symbolique vivante)
- [x] `axiom.providers` & `axiom.illustrations` (pilotes d'inférence LLM, génération d'images et hooks Universe-as-Code)
- [x] Interfaces Utilisateurs (`axiom.ui.web`, `axiom.ui.qt`, `axiom.cli`) & extensions transversales (i18n, aide, safe-mode)

## Phase 3 — Patches outillés (✅ TERMINÉE)
- [x] Trampolines `@patchable` (before, after, around) et sentinelle `ShortCircuit`
- [x] Mécanisme de secours par substitution de bytecode (`__code__` swapping) préservant l'identité d'objet
- [x] Enregistrement réversible `ctx.patch()` et restauration intégrale au `ctx.cleanup()` (D11)
- [x] Gel d'exécution par step (§6.2.3, `step_patch_freeze()`, `PatchingDuringStepError`)
- [x] Inspection CLI (`axiom mods patches`) et validation statique (`axiom mod validate`)

## Phase 4 — Création de mods (outils + créateur LLM) (✅ TERMINÉE)
- [x] Échafaudage de mods `axiom mod new` (`axiom/kernel/scaffold.py`) : archétypes hook, slot, data
- [x] Testeur de mod unifié `axiom mod test` (`axiom/kernel/tester.py`) : validation manifestes, vérification D4 imports UI, runner pytest borné
- [x] Mode développement à chaud `axiom mod dev` (`axiom/kernel/dev.py`) : watcher mtime, dépilage D11 et rechargement
- [x] Créateur de mods par LLM `axiom mod generate` & API Web (`axiom/kernel/llm_creator.py`) : staging sandbox, diffs, tests automatiques et garde-fous de confirmation (§12, D14)

## Phase 5 — Store, Dépendances, Licence & Distribution (✅ TERMINÉE)
- [x] Protocole du Store distant (`axiom/kernel/store.py`) : catalogue d'index, recherche, installation, vérification stricte du hash SHA-256 (`ModIntegrityError`)
- [x] Vérification déclarative des dépendances Python légères (`axiom/kernel/dependencies.py`, `[python].requires`, Règle D-7)
- [x] Cadre juridique et licence des mods (`docs/licensing_mods.md`, `NOTICE`, Règle D-9 & §14)
- [x] Packaging PyPI headless micro-kernel (`export_engine.py`, exclusion mods/UI, Règle D-8) et passage à la version 1.0.0
- [x] Commandes CLI (`axiom mods search`, `axiom mods install`, `axiom mods update`)
- [x] Endpoints API Web (`GET /api/store/search`, `POST /api/store/install`)
- [x] Catalogue officiel initial d'index (`dist/mods/store_index.json`)
- [x] Suite de tests dédiée (`tests/test_mod_store_and_packaging.py`) — 9/9 tests au vert
