---
name: project-qa-post-17h59
description: QA 2026-09-22 des commits d'autres contributeurs (Frosoore, Boss Baby) après cb9e56d — pannes trouvées, pièges techniques, ce qui reste ouvert
metadata:
  type: project
---

**Contexte.** Après `cb9e56d` (2026-06-25, dernier commit « propre » de l'utilisateur), 7 commits de
**Frosoore** (Gemini CLI) et **Boss Baby** (`4967506`, 74 fichiers / 10k lignes, message fourre-tout)
ont cassé le GUI, la 1ʳᵉ compilation de Myria et la CI, sans suivre la méthodo (pas de ligne
`AXIOM_STATUS.md`, dossiers d'étape non indexés, tickets non tracés). QA + correctifs le 2026-09-22 :
`maintenance/qa/qa-post-17h59-2026-09-22/` puis `maintenance/qa/tickets-092-098-2026-09-22/`.

**Why:** l'utilisateur se méfie à raison des commits des autres contributeurs ; il faut les auditer
systématiquement (idéalement plusieurs sous-agents Sonnet en parallèle, un par commit/zone).

**How to apply:**
- À la reprise après une absence : `git log` par auteur depuis le dernier commit de l'utilisateur,
  auditer chaque commit non-utilisateur (bugs, sécurité web, i18n ×10, méthodo).
- Pièges techniques retenus : ne **jamais** surcharger `QApplication.notify` en Python (interblocage
  avec le thread `QAudioContext` → fenêtre jamais affichée) ; `PRAGMA defer_foreign_keys` n'a d'effet
  qu'**après** `BEGIN` ; tester une compilation d'univers **sans cache** (le cache local masque les
  bugs de 1ᵉʳ lancement) ; toute clé i18n EN doit exister dans les 10 langues (CI).
- TICKET-095 réglé le 2026-09-22 (feu vert utilisateur) : `Inventory_Snapshots`, le rewind restaure
  l'inventaire ; toute mutation d'inventaire hors tour doit appeler `snapshot_present_inventory`.
  Verbosité par défaut = `balanced` (choix utilisateur).
- L'utilisateur veut que les tickets finis quittent `PENDING.md` pour `DONE.md` (vérifier aussi les
  anciens tickets marqués ✅ restés listés).
- Voir [[project-parallel-dev-handover]], [[feedback-maintenance-workflow]], [[project-status-doc-convention]].
