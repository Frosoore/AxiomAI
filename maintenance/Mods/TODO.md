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
- [ ] 0a. Harnais « golden step » (faux LLM scripté, N tours → rewind → fork → export → comparaison)
- [ ] 0b. Fin de tour unique dans `Session` (mémoire living Qt/web unifiée, auto-canonize)
- [ ] 0c. Un seul rewind + registre des données de save (fin des 5 listes de tables)
- [ ] 0d. Tour transactionnel + époques de session
- [ ] 0e. Config ouverte (`[mods.<id>]`) + version de schéma + migrations + retrait des CHECK figés
- [ ] 0f. Découpage de `process_turn` en étapes nommées

## Phase 1 — Noyau
- [ ] Chargeur + manifeste `mod.toml` + registre (exclusif / chaîne / collecte) + hooks + `ModContext`
- [ ] Stockage par politiques + modpack + mode sans échec + CLI `axiom mods`
- [ ] Évaluer `pluggy` comme brique interne
- [ ] Premier mod officiel extrait (petite feature) pour valider

## Phase 2 — Features en mods officiels
- [ ] `axiom.world`, `axiom.turn`, temps, mémoire(s), inventaire, stats dynamiques, providers, UI

## Phase 3 — Patches outillés
## Phase 4 — Création de mods (outils + créateur LLM)
## Phase 5 — Store (licence, installeur pip)
