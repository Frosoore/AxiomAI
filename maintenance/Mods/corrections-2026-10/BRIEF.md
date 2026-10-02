# Brief commun — corrections de la branche `mods` (octobre 2026)

## Contexte
Axiom AI (`/home/garen/coding/AxiomAI`, branche **`mods`**, ne change PAS de branche) : moteur de JDR
narratif piloté par LLM, en cours de transformation en « noyau minimal + mods ». La vision de référence
est `git show e0ad4be:maintenance/Mods/DOC.md` (lis §2 garde-fous D1→D17, §4, §6, §7, §10, §12).
Une revue en 4 rapports vient d'être faite : `maintenance/Mods/review-2026-10-03/` (`0-SYNTHESE.md`
puis `1-NOYAU.md`, `2-PHASE0.md`, `3-MODS.md`, `4-DOC-ET-RUNTIME.md`). **Lis la synthèse et les
sections des rapports qui concernent ton lot** : chaque problème y a ses preuves `fichier:ligne`
et une correction proposée. Re-vérifie toujours dans le code avant de corriger (les lignes ont pu bouger).

Le propriétaire ne code pas. Il pilote via des agents. Il a validé ces corrections.

## Règles impératives
- **Pas de commit, pas de stage, pas de changement de branche, pas de stash.** Le propriétaire gère git.
- **Ne supprime AUCUN fichier de test.** Ne supprime aucun autre fichier sauf si ton lot l'autorise
  explicitement ; sinon liste-le dans ton rapport comme « suppression proposée ».
- D'autres agents travaillent **en même temps** sur d'autres fichiers du même dépôt. Ne modifie QUE les
  fichiers de ton périmètre. Si un correctif exige de toucher un fichier hors périmètre, ne le fais pas :
  note-le dans ton rapport (« à faire par le lot X »). Si un test casse à cause d'un fichier hors de ton
  périmètre en cours de modification, relance un peu plus tard avant de conclure.
- **Aucun test ne doit lire ni écrire la vraie config de l'utilisateur** (`~/.config/AxiomAI`) ni ses
  données (`~/AxiomAI`) : lance toujours pytest et tes scripts avec
  `AXIOM_CONFIG_DIR=$(mktemp -d) AXIOM_DATA_DIR=$(mktemp -d)` en plus des fixtures.
- Tests : `.venv/bin/python -m pytest <fichiers> -q`. Jamais toute la suite d'un coup (segfault
  TICKET-067 : Qt multimédia puis torch dans le même processus). Par fichiers / petits lots.
- Édition chirurgicale : pas de reformatage hors sujet, style du code environnant, commentaires sobres.
- Pas de sur-ingénierie de sécurité (D14) : on corrige l'ordre et la vérité, on n'ajoute pas de sandbox.
- Chaque correctif important est couvert par un test (nouveau ou adapté) qui échouait avant.
- Scripts temporaires uniquement dans `/tmp/claude-1000/axiom-fix/`.

## Rapport
Écris `maintenance/Mods/corrections-2026-10/<ton-lot>.md` :
1. Corrigé : pour chaque point de la revue (avec son identifiant, ex. `1-NOYAU B1`) — ce qui a été
   changé (`fichier:ligne`), le test qui le prouve.
2. Non corrigé / partiel : pourquoi, et ce qu'il reste à faire.
3. Résultats de tests exécutés (commandes + compte passés/échoués).
4. Suppressions proposées, fichiers hors périmètre à toucher, questions pour le propriétaire.
Réponds ensuite avec le chemin du rapport et un résumé de 8 lignes max.
