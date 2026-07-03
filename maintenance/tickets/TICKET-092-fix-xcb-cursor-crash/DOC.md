# DOC — TICKET-092-fix-xcb-cursor-crash

## Objectif
Empêcher un crash brutal (core dumped) au lancement de l'application dû à l'absence de la bibliothèque système `libxcb-cursor0` (exigée par PySide6 >= 6.5.0 sous Linux/X11).

## Solution technique
1. Ajouter une étape de vérification système dynamique dans [debug/startup_check.py](file:///home/frosoore/AxiomAI/debug/startup_check.py). Si `libxcb-cursor.so.0` est introuvable (via `ldconfig` et `ctypes.util.find_library`), bloquer le démarrage avec un message d'erreur clair et les commandes d'installation pour les principales distributions Linux.
2. Améliorer la vérification préliminaire dans [run.sh](file:///home/frosoore/AxiomAI/run.sh) pour fournir également la commande d'installation adéquate.
