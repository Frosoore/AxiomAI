# QA post-`cb9e56d` (2026-09-22)

**Objectif.** Remettre `main` d'aplomb après 7 commits d'autres contributeurs (Frosoore / Boss Baby)
qui n'ont pas suivi la méthodo, et corriger les 3 pannes signalées (GUI figé, FOREIGN KEY Windows,
CI i18n). Les findings non corrigés ici partent en tickets dans `maintenance/PENDING.md`.

**Décision technique (GUI).** Ne jamais surcharger `QApplication.notify()` en Python dans ce projet
(multimédia + threads Qt internes → interblocage GIL). Pour un comportement global, utiliser un
`installEventFilter` sur l'application.
