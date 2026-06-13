---
name: project-beta-launch
description: Cap projet décidé le 2026-06-12 — recruter des bêta-testeurs (app + lib), préparation dans TICKET-062
metadata:
  type: project
---

**Décision utilisateur (2026-06-12) : le projet part en recrutement de bêta-testeurs** (app GUI
+ lib `axiomai-engine`, voire petits collaborateurs). Toute la préparation est spécifiée dans
**`maintenance/PENDING.md` → TICKET-062** : univers par défaut fondé sur **Myria** (fiction perso
de l'utilisateur — **item 1 FAIT le 2026-06-12** : univers créé `universes/Myria/` + installation
au 1ᵉʳ lancement câblée via `core/bundled_universes.py`, reste relecture canon + commit ; ⚠ sur
SA machine le Hub montrait 2 « Myria », vieux db de test supprimé par lui le 2026-06-12),
clés Fireworks.ai embarquées temporairement — **item 2 FAIT le 2026-06-12** : 4 clés AXIOMAI-0..3
(2×6 $ + 2×1 $, ⏰ **expirent le 2026-06-30** → retirer/renouveler le pool ensuite) obfusquées
dans `core/builtin_keys.py`, rotation auto, plafond modèles pas chers, bouton « Parcourir » les
modèles, 1ᵉʳ lancement zéro-config → fireworks/`gpt-oss-120b` (l'ancien défaut deepseek-v3p1 est
mort chez Fireworks). **Item 4 (outil de diagnostic) FAIT — CLI + GUI Aide→Diagnostic.**
**Items 1, 2, 4 VALIDÉS GUI par l'utilisateur le 2026-06-13.** TICKET-050 (fail-fast 429) FAIT
et **CI GitHub Actions FAITE** (`.github/workflows/tests.yml`, 2 lots, matrice 3.11/3.12 — reste
à confirmer verte au 1ᵉʳ push). **Restent uniquement : vérif du support Windows** (censé marcher,
`run.bat` existe, jamais testé récemment — audit code seulement, pas de machine) **+ nouvelles
captures + GIF** (les assets du README datent).

**TICKET-066 — chemin de raisonnement VALIDÉ de bout en bout le 2026-06-12** (bloquant bêta :
gpt-oss = modèle de raisonnement → Timekeeper crashait, narration vide, « Generating »
interminable) : fix backend = floor `max_tokens=2048` + `reasoning_effort: low` + tolérance
`content` absent dans `axiom/backends/universal.py`. Vérifié en réel : streaming gpt-oss-20b
(1ᵉʳ token ~2 s) ET tour complet sur Myria via `Session` (= chemin GUI), narration streamée
identique à la finale (pas d'avalement de fence JSON). **L'échec GUI répété (« ça marche pas »
/ « la réponse n'arrive pas ») n'était PAS le backend → TICKET-068** : le 1ᵉʳ tour de chaque
session figeait ~87 s parce que le modèle d'embedding `all-MiniLM-L6-v2` faisait un HEAD réseau
vers HF Hub à chaque chargement, qui stalle sur l'IPv6 cassée de la machine (même cause que le
fix Gemini `IPv4FirstTransport`, indépendant du backend LLM). Corrigé par `local_files_only=True`
dans `axiom/memory.py::_EmbeddingSingleton` (essai offline → fallback online unique si pas
caché) : 86,7 s → 3,2 s, tour Myria 1ᵉʳ token à 3,9 s. **TICKET-066 + TICKET-068 VALIDÉS GUI le
2026-06-13** (gel disparu, narration reasoning OK). Au passage : segfault de suite préexistant
consigné en TICKET-067.

Canaux visés : SillyTavern (l'app importe leurs cartes — à mettre en avant dans le README),
r/LocalLLaMA, LinuxFr.org, itch.io, Show HN/r/Python pour la lib. Conseillé avant annonce :
TICKET-050 (fail-fast 429) + CI tests.

Lié : [[project-doc-chantier]] (doc finie = prérequis rempli), [[project-engine-split-strategy]]
(PyPI 0.1.3 prêt à publier, page EN + lien doc).
