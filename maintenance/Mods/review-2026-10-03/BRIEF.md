# Brief commun — revue de la branche `mods` (2026-10-03)

## Contexte
Axiom AI (repo `/home/garen/coding/AxiomAI`) : moteur de JDR narratif piloté par LLM, Python.
Le propriétaire ne code pas (il pilote via des agents IA). Il a validé le 2026-09-26 une vision
« noyau minimal + mods » (Minecraft Fabric/Forge, load order Skyrim). Son associé Frosoore (qui code
via des agents IA, Gemini notamment) a implémenté le chantier sur la branche **`mods`** :
4 commits (`659c21b`, `82f29e1`, `fa03320`, `3f100ed`), ~26 000 lignes ajoutées, 406 fichiers.
Base de comparaison : `main` (merge-base `e0ad4be`). Son `maintenance/Mods/TODO.md` déclare TOUTES
les phases 0 à 5 terminées (assainissement, noyau, extraction de toutes les features en mods,
patches, créateur LLM, store).

## Documents de référence (à lire)
- **La vision validée, version d'ORIGINE** (avant modifications de Frosoore) :
  `git show e0ad4be:maintenance/Mods/DOC.md` — c'est LA référence. Lis surtout §1 (objectif),
  **§2 (garde-fous D1→D17 contre les dérives)**, §4 (noyau), §6 (niveaux/patches), §7 (emplacements),
  §10 (saves/stockage), §13 (feuille de route), §14 (décisions).
- `maintenance/Mods/DOC.md` actuel : Frosoore l'a modifié (+265 lignes) ; toute divergence avec la
  version d'origine est à signaler si elle change la vision sans décision tracée.
- `maintenance/Mods/CRITIQUE.md` et `ARBITRAGE.md` : revue d'avant-implémentation (problèmes connus,
  dont les tickets TICKET-100→105 de `maintenance/PENDING.md`).
- Les sous-dossiers `maintenance/Mods/phase-*/` et autres : DOC/TODO/CHANGELOG de Frosoore par phase.
- `ARCHITECTURE.md` (règles moteur) ; `mods/` (les mods) ; `axiom/kernel/` (le noyau) ; `axiom/`.

## Règles pour toi
- **Ne modifie AUCUN fichier du repo** sauf ton rapport. Pas de commit, pas de stage, pas de checkout
  de branche. Tu peux écrire des scripts temporaires uniquement dans `/tmp/claude-1000/axiom-review/`.
- Lis le **code**, pas seulement la doc : la doc d'un agent IA peut affirmer des choses fausses.
  Chaque affirmation de ton rapport s'appuie sur `fichier:ligne` ou sur une commande exécutée.
- Distingue clairement : **vérifié en exécutant** / **vérifié en lisant** / **supposé**.
- Tests : `.venv/bin/python -m pytest <fichiers> -q`. Ne lance JAMAIS toute la suite d'un coup
  (segfault connu TICKET-067 quand Qt multimédia précède torch) : par lots/fichiers.
- Sois franc mais juste : signale aussi ce qui est bien fait. Pas de mauvaise foi.
- Rédige en français. Le propriétaire ne code pas : chaque point important a une phrase simple
  « ce que ça veut dire concrètement ».

## Format du rapport
1. Verdict (5-10 lignes).
2. Ce qui est bien fait (preuves).
3. Problèmes, triés par gravité (**bloquant / important / mineur**), chacun : titre, constat +
   preuves `fichier:ligne`, garde-fou ou décision du DOC violé le cas échéant (D1…D17, D-1…D-9),
   conséquence concrète, correction proposée.
4. Écarts entre ce que la doc/TODO affirme et ce que le code fait réellement.
5. Questions pour Frosoore / le propriétaire.
