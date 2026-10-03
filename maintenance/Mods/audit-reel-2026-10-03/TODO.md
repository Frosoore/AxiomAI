# TODO — Audit réel 2026-10-03

Constats détaillés : `DOC.md` (identifiants entre crochets = section du DOC).

## Audit
- [x] Lire ETAT_REEL, TODO, synthèse + rapports, corrections-2026-10, DOC (vision)
- [x] Relancer la suite comme la CI (config isolée) et bissecter l'échec
- [x] Vérifier dans le code / par sonde chaque point déclaré fait
- [x] Rapport `DOC.md`

## Corrections proposées (en attente du feu vert du propriétaire)
### Bloquant
- [ ] [3.3/K6] Isoler le parsing des sections de prompt (un tuple mal formé ne doit plus faire échouer le tour) + test sur le vrai tour
- [ ] [4.1] `[storage]` : lire `table`, refuser les politiques inconnues, corriger les déclarations fausses des manifestes officiels (`axiom.time` → `Scheduled_Events` !, living_memory, inventory, world) — ou retirer la lecture tant que ce n'est pas juste
- [ ] [4.2] `ctx.store` : corriger le plantage set/delete/set, pas de `step=0` implicite, écritures dans le `TurnWriteBatch`
- [ ] [2] `test_image_generator` dépendant de l'ordre + appel réseau Timekeeper
- [ ] [3.4/M3] `main.py` / `cli/play.py` : tester le statut réel du mod UI, pas seulement le choix utilisateur
### Important
- [ ] [1] Décision lot E (code rapatrié dans le noyau) — question 1
- [ ] [4.3] Clés i18n de l'écran des mods + raison réelle d'un mod rejeté
- [ ] [3.3/K10] Modpack : hash, avertissement visible en UI, CLI sans registre, `get_connection` au lieu de `sqlite3.connect`, plus d'`except: pass`
- [ ] [3.7] `test_canonical_mod_example` : jouer un vrai tour (la sonde du DOC §3.7 peut servir de base)
- [ ] Tests manquants : 088, migrations, époques, 0d, Chroma après commit, fork comparé à la source au tour N
- [ ] Remettre `TODO.md` / `PENDING.md` en accord avec le code (088/102/103 faits ; lot E, K9, M2, M7, M8 non)
### Mineur
- [ ] [3.2/0b] Restes Qt morts (`_fact_pending`, `_accumulate_and_maybe_extract`, `workers/fact_worker.py` → suppression à valider)
- [ ] [3.4/M5] Schéma JSON en double + inventaire codé en dur dans `axiom.turn`
- [ ] [4.4] fuite `RagService`, illustrations sans `data_dir`/fork, écouteurs de patch cumulés
