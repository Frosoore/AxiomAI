# TODO — QA post-merge (Companion Mode + génération d'images)

Contexte : deux merges récents sur main (`4bc313d` temps causal, `9814896` Companion/images
depuis origin/main dans dev-0) avec résolutions de conflits manuelles. Objectif : contrôle
qualité complet, surtout sur les features récentes, pour vérifier que rien n'a cassé.

- [x] Vérifier l'absence de marqueurs de conflit résiduels (<<<<<<< etc.) — aucun
- [x] Compiler tout le projet (py_compile) + `debug/startup_check.py` — OK
- [x] Vérifier la frontière headless (pas d'import Qt dans `axiom/`, test_engine_headless) — OK
- [x] Inspecter les artefacts suspects du merge : `fix_tests.py`, `fix_tests2.py`,
      `refactor_tests.py` (racine), fichiers binaires `turn_1.png` commités → TICKET-044
- [x] Revue de `axiom/session.py` (fichier de collision principal) → TICKET-043, 047
- [x] Revue de `axiom/arbitrator.py`, `axiom/prompts.py` (nouvelle API intents=) —
      tous les appelants alignés (CLI play, workers, multiplayer, regenerate) ; un test
      oublié par le merge (`test_engine_port_b4.py`) corrigé dans cette étape
- [x] Revue de `axiom/image_generator.py` + config + branchement UI → TICKET-045, 046, 048 ;
      config Réglages vérifiée sans perte de champ (TICKET-031 préservé)
- [x] Revue du Companion Mode (contexte Héros enrichi) — câblage GUI/CLI complet ; seul
      défaut : id joueur en dur (TICKET-043)
- [x] Lancer les suites de tests par sous-ensembles — 580 verts au total après le fix
- [x] Consigner chaque problème trouvé en ticket dans `maintenance/PENDING.md` (043→048)
