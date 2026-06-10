# TODO — Correction en lot des tickets QA post-merge (043→048)

Feu vert utilisateur du 2026-06-10 : corriger les 6 tickets d'affilée.

- [x] TICKET-044 — supprimer les artefacts du merge (3 scripts racine + 2 PNG assets/)
- [x] TICKET-047 — `_load_history` : format groupé seulement si plusieurs intentions
- [x] TICKET-043 — résoudre l'id joueur réel dans `session.py` (Héros + images)
- [x] TICKET-045 — échec backend image → None (mock réservé au backend "mock")
- [x] TICKET-046 — onglet Illustration : passer par `axiom/localization.py` / `tr()`
- [x] TICKET-048 — cycle de vie des images : fork/suppression/pack/unpack/rewind
      (+ mort hardcore) ; tranché : pas d'images sur le chemin multijoueur
- [x] Tests : suites par sous-ensembles vertes (596 au total) + 8 nouveaux tests
- [x] Doc : CHANGELOG, PENDING → DONE, index README
