---
name: project-mods-system
description: Chantier « système de mods » (.axmod) — vision validée 2026-09-26, pas encore de code ; où lire, décisions clés, ordre imposé
metadata:
  type: project
---

Axiom devient **« noyau minimal + mods »** (modèle Minecraft Fabric/Forge + load order Skyrim) : le
tour de jeu, les UI, les providers, la mémoire… deviennent des mods ; le noyau ne connaît ni le JDR,
ni les LLM, ni les UI. Vocabulaire : **« mod »**, fichier **`.axmod`**.

Tout est dans `maintenance/Mods/` : `DOC.md` (référence : vision §1, **garde-fous D1→D17 §2**,
feuille de route §13, registre des décisions §14), `CRITIQUE.md`, `ARBITRAGE.md`, `TODO.md`.

**Why:** l'utilisateur veut que la doc empêche toute dérive vers un système moins bien (noyau qui
grossit, mods officiels privilégiés, profondeur sacrifiée, sécurité/résilience ajoutées alors qu'elles
sont explicitement écartées).

**How to apply:**
- Lire `maintenance/Mods/DOC.md` en entier avant de toucher au tour, au rewind, aux saves ou à la config.
- Ordre acté : bugs TICKET-100→105 d'abord, puis **phase 0 « assainir le moteur »** (harnais golden
  step, fin de tour dans `Session`, rewind unique + registre des données de save, tour transactionnel,
  config/schéma ouverts, découpage de `process_turn`) **avant** tout chargeur de mods.
- Non-objectifs assumés : pas de sécurité/sandbox, pas de résilience des saves, pas de trieur imposé.
- Pendant le découpage du tour : propriétaire unique de `arbitrator.py`/`session.py` (à caler avec
  Frosoore, cf. [[project-parallel-dev-handover]]).

**Mise à jour 2026-10-03 :** Frosoore a implémenté le chantier sur la branche `mods` (4 commits,
TODO « tout ✅ »). Revue par 4 agents → `maintenance/Mods/review-2026-10-03/0-SYNTHESE.md` :
direction bonne mais **pas mergeable** — « tour = mod » est une façade (`arbitrator.py` resté dans
le noyau), le noyau dépend des mods via proxys, régressions (boucle de correction, erreurs masquées,
fork qui perd la mémoire living), licence des mods tranchée sans le propriétaire. ⚠ Les tests mods
écrivent dans la vraie `~/.config/AxiomAI/settings.json` (fixture n'isole pas la config).
