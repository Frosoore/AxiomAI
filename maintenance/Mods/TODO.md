# TODO — Système de mods

> Référence : `DOC.md` (vision, garde-fous §2, feuille de route §13). **État réel détaillé et
> justification de chaque case : `ETAT_REEL.md`** (identifiants entre crochets).
> Révisé le 2026-10-03 après la revue de la branche `mods` : les cases cochées par Frosoore sans
> comportement vérifié ont été **décochées**. Règle désormais : **une case ne se coche qu'avec un test
> qui prouve le comportement promis par la vision.**
> Légende : `[x]` fait et vérifié · `[~]` partiel (voir ETAT_REEL) · `[ ]` à faire.

## Cadrage
- [x] Vision validée → `DOC.md`
- [x] Critique → `CRITIQUE.md` ; arbitrage → `ARBITRAGE.md`
- [x] Décisions D-1 → D-9 (2026-09-26)
- [x] Revue de l'implémentation (2026-10-03) → `review-2026-10-03/`, `ETAT_REEL.md`

## Préalable — bugs confirmés (D-1)
- [~] TICKET-100 — rewind ChromaDB OK ; reste ids déterministes + rollback Chroma après le commit SQL
- [x] TICKET-101 — tour échoué/annulé : plus de message orphelin (vérifié en exécutant)
- [~] TICKET-102 — web OK ; Qt contourne `Session.rewind` (époque non incrémentée)
- [~] TICKET-103 — `Session_Lore` OK ; `Fired_Scheduled_Events` toujours copiés sans filtre
- [ ] TICKET-104 — `regenerate.py` inchangé
- [ ] TICKET-105 — « résolu » par une régression (boucle de correction morte) → à refaire proprement [M4]
- [ ] TICKET-088 — le fork perd toujours la mémoire living, sans erreur [0c]
- [x] TICKET-089 (étendu)

## Coordination (D-6)
- [ ] Propriétaire unique de `arbitrator.py`/`session.py` formalisé dans `maintenance/collab/`
- [ ] Statut de `Multiplayer/` (fini ou gelé)

## Corrections d'octobre (voir `ETAT_REEL.md` §7)
- [x] Lot A — tests hermétiques (config, `dist/`, Ollama, Quick Tour) + CI adaptée + import web
- [x] Lot C — noyau (conflits, statut, ordre, versions, isolation, à chaud, safe mode, découverte, `.axmod`, patches, créateur LLM)
- [x] Décisions prises sans le propriétaire annulées (clause `NOTICE`, en-tête/bilan du DOC, licence = question ouverte)
- [~] Lot B (B1 saves/rewind, B2 tour) — arrêté en cours, voir `ETAT_REEL.md` §8
- [ ] Lot E — vraie phase 2 (déplacer le tour et les features dans leurs mods, supprimer les proxys)
- [ ] Doc (exemple de mod qui marche, README, ARCHITECTURE, STATUS, Changelog, PENDING)

## Phase 0 — Assainir le moteur (≈ 75 %)
- [~] 0a. Harnais golden — existe ; état comparé trop étroit, pas de fork à mi-partie, non hermétique
- [~] 0b. Fin de tour unique — mémoire living OK ; auto-canonize encore dans Qt + web ; logique de jeu dans `main_web.py`
- [~] 0c. Rewind unique + registre — registre OK ; rewind Qt séparé ; fork amnésique ; fork non générique
- [~] 0d. Tour transactionnel + époques — OK sauf `Item_Definitions` écrit hors tampon et gardes d'époque incomplètes
- [~] 0e. Config/schéma ouverts — config + CHECK OK ; migrations par mod jamais appelées
- [~] 0f. Découpage du tour — étapes réelles ; deux orchestrations ; `gather_context` appelé deux fois

## Phase 1 — Noyau (squelette)
- [~] Chargeur + manifeste — manifeste, tri des dépendances OK ; conflits qui vident tout, versions et ordre utilisateur ignorés [K1–K4]
- [~] Registre exclusif / chaîne / collecte — collecte/chaîne OK ; exclusif = « premier arrivé » [K3]
- [~] Hooks — appelés ; isolation inversée (erreurs avalées, mod fautif jamais désactivé) [K5, K6]
- [~] `ModContext` — existe ; `cleanup` jamais appelé en prod, pas d'API publique de lecture, pas de jobs [K7, K11]
- [ ] Stockage par politiques (`ctx.store`, `versioned_kv`, `[storage]` lu) [K9]
- [ ] Modpack enregistré dans la save et les exports [K10]
- [~] Mode sans échec — existe mais garde les mods `axiom.*`/`core.*` [K8]
- [x] CLI `axiom mods` utilisable sans UI
- [x] `pluggy` évalué et écarté
- [ ] Noyau neutre (ni LLM, ni JDR, ni config applicative) [K12]

## Phase 2 — Features en mods officiels (façade)
- [ ] `axiom.turn` contient réellement le tour (aujourd'hui coquille autour de `axiom/arbitrator.py`) [M2]
- [ ] Le noyau n'importe plus rien de `mods/` (6 proxys à supprimer) [M1]
- [~] `axiom.world` — règles déplacées ; boucle de correction cassée [M4]
- [~] `axiom.time`, `axiom.inventory`, `axiom.rag`, `axiom.living_memory`, `axiom.illustrations`, `core.stat_dynamics` — décochables un par un (vérifié) ; code encore importé par le noyau
- [ ] `axiom.providers` effectif (aujourd'hui les UI construisent le LLM elles-mêmes) [M8]
- [~] UI en mods (`axiom.ui.qt`, `axiom.ui.web`, `axiom.cli`) — lanceurs ; emplacements web non lus ; dépendance `help_system` non déclarée [M7]
- [ ] Mod « chat minimal » (installation « tout décoché ») [M3]
- [~] Emplacements du tour — consultés ; contribution au schéma JSON et sections positionnées manquantes [M5, M6]

## Phase 3 — Patches outillés
- [x] Trampolines `@patchable` (before/after/around, `ShortCircuit`) sur fonctions, from-import capturés
- [~] Secours `__code__` — fonctions simples OK ; méthodes et closures échouent en silence [P1]
- [ ] Refus bruyant des cibles introuvables, aucun patch inactif listé [P1, P3]
- [ ] Points `@patchable` dans le moteur [P2]
- [~] Gel pendant un step — non réentrant [P4]
- [~] `axiom mods patches` / `axiom mod validate` — existent ; listent des patches inactifs

## Phase 4 — Création de mods
- [~] `axiom mod new` — existe ; modèles branchés sur des hooks inexistants [C2]
- [~] `axiom mod test` — existe ; n'utilise pas le harnais golden [C3]
- [x] `axiom mod dev` (rechargement à chaud en dev)
- [ ] Créateur LLM : aucune exécution avant confirmation, écriture confinée [C1]
- [ ] Créateur LLM sorti du noyau (mod) [C4]

## Phase 5 — Store, dépendances, licence, distribution (gelée)
- [x] Vérification déclarative `[python].requires`, sans installeur (D-7)
- [~] Client de store (recherche/installation, SHA-256) — sans catalogue ni serveur ; installe dans les sources [S3, S4]
- [ ] Licence des mods — **question ouverte** (avis juridique requis ; clause retirée de `NOTICE`) [S2]
- [ ] Paquet PyPI « noyau seul » fonctionnel — **ne pas publier la 1.0.0 en l'état** [S5]
