# Revue de la branche `mods` — Synthèse (2026-10-03)

> Synthèse des 4 rapports de ce dossier (`1-NOYAU.md`, `2-PHASE0.md`, `3-MODS.md`,
> `4-DOC-ET-RUNTIME.md`), revus sur les commits `659c21b` → `3f100ed` (Frosoore) contre la vision
> d'origine (`git show e0ad4be:maintenance/Mods/DOC.md`). Les détails et preuves `fichier:ligne`
> sont dans les rapports ; ici, seulement le verdict et la liste de travail priorisée.

## Verdict

**La direction générale est la bonne, mais la branche n'est pas mergeable en l'état. Le `TODO.md`
surestime fortement l'avancement.**

Ce qui est réel et de bonne qualité :
- l'assainissement du moteur (phase 0) a vraiment été fait : registre des tables, tour validé en un
  seul commit, époques de session, harnais golden. TICKET-101 et 089 sont corrigés, et le rewind de
  ChromaDB marche sur le web et la CLI ;
- le noyau est petit et lisible. Le manifeste, le tri des dépendances, `@patchable` et la CLI sans UI
  fonctionnent ;
- on peut décocher les mods de feature (inventaire, temps, mémoires, illustrations, stats) un par un
  et le tour joue quand même. Les emplacements (sections de prompt, champs de sortie, filtres,
  backend) sont vraiment consultés ;
- l'app tourne (Qt, web, CLI). Sur 1 187 tests, 1 183 passent, et aucun test de `main` n'a été
  supprimé.

Ce qui est faux par rapport à la vision :
- **« Le tour est un mod » est une façade.** `mods/axiom.turn` (177 lignes) appelle
  `axiom/arbitrator.py` (1 955 lignes), resté dans le noyau. Environ 9 400 lignes de JDR/LLM sont
  encore dans `axiom/`.
- **Le noyau dépend des mods (D1 inversé).** Six modules du noyau sont des proxys vers `mods.*`. Sans
  `mods/`, le noyau ne sait même plus compiler un univers. Le paquet PyPI « noyau seul » est donc cassé.
- **Plusieurs promesses sont cochées mais simulées :** l'ordre choisi par l'utilisateur, les versions,
  la réversibilité (`cleanup` jamais appelé), l'activation à chaud, le mode sans échec (il garde tous
  les mods `axiom.*`), le stockage par politiques (`ctx.store` et `versioned_kv` n'existent pas), les
  migrations (jamais appelées), et les patches sur les méthodes (échec silencieux).

## Points urgents (à régler avant tout le reste)

1. **Les tests écrivent dans la vraie config de l'utilisateur.** La fixture `isolated_axiom_data_dir`
   isole les données mais **pas** `~/.config/AxiomAI/settings.json`.
   `test_mod_store_and_packaging.py` (install `enable=True`) et `test_mods_dialog_ui.py` (toggle)
   y écrivent. Constaté pendant la revue : `settings.json` a été modifié à 00:12, et `mod_settings`
   contient `community.herbalism`, `community.lockpicking`, `community.testpack`.
   → Isoler aussi le dossier de config dans les tests. **Le propriétaire doit vérifier ses réglages**
   (backend, clés).
2. **Trois régressions vérifiées :**
   - la boucle de correction de l'Arbitre est morte, car `axiom.turn` recrée le moteur à chaque tour ;
   - toute exception d'un mod, ou une erreur LLM, annule le tour avec un message générique (« LLM
     injoignable » n'apparaît plus) ;
   - **un fork de save perd toute la mémoire living sans erreur** : des `uuid4` sont écrits dans des
     colonnes entières, et l'erreur est avalée par `except: pass`.
3. **Le chargeur : un seul conflit ou un seul cycle désactive TOUS les mods**, tour compris, avec une
   seule ligne de log.
4. **CI cassée sur un clone propre** : des tests lisent `dist/` (non versionné), un test Qt réactive le
   segfault TICKET-067, et `main_web.py:2859` importe un module inexistant (`axiom.kernel.bootstrap`),
   donc les mods ne se chargent pas au démarrage du serveur web.
5. **Le créateur LLM exécute le code généré avant la confirmation** et peut écrire hors de son
   dossier. C'est la seule protection que §12 prévoyait, et elle est contournée.

## Décisions prises sans le propriétaire (à annuler ou à faire valider)

- **Licence des mods** : une clause ajoutée à `NOTICE` autorise des mods tiers propriétaires, en
  s'appuyant à tort sur AGPL §7(b). La vision exigeait la décision du propriétaire **et** un avis
  juridique (D-9). → À retirer en attendant.
- **Store construit** alors que §13 le plaçait après la licence et l'installeur. Son catalogue
  `dist/mods/store_index.json` n'est pas dans le repo. → À marquer expérimental.
- **En-tête du `DOC.md` passé à « FINALISÉE ET VALIDÉE »** sans entrée dans le registre §14. Les garde-fous
  D1→D17 n'ont pas été modifiés, ce qui est bien.

## Liste de travail priorisée

| Prio | Sujet | Quoi faire |
|---|---|---|
| P0 | Hygiène | Isoler la config dans les tests ; aucun test ne lit ni n'écrit `dist/` ; CI verte sur un clone propre ; corriger l'import `axiom.kernel.bootstrap` |
| P0 | Régressions | Boucle de correction ; erreurs LLM et mods qui remontent avec leur vrai message ; fork qui garde la mémoire living (et retirer les `except: pass`) |
| P1 | Décisions | Retirer la clause de licence de `NOTICE` ; store « expérimental » ; en-tête du DOC remis à l'état réel |
| P1 | Vérité du suivi | `TODO.md` remis à l'état réel (voir ci-dessous) ; statuts TICKET-100→105 mis à jour dans `PENDING.md` |
| P2 | **Vraie phase 2** | Déplacer **réellement** `arbitrator.py`, le monde, le temps, l'inventaire, la mémoire… **dans** leurs mods ; supprimer les proxys ; le noyau n'importe plus rien de `mods/` (vérification automatique, pas `check_headless` qu'on contourne avec `importlib`) |
| P2 | Chargeur | Un conflit isole le mod fautif, pas tout ; ordre utilisateur ; versions `axiom_api` et dépendances vérifiées ; mode sans échec = zéro mod ; `cleanup()` réellement appelé ; un hook qui plante désactive son mod ; découverte indépendante du dossier courant |
| P2 | Créateur LLM | Confirmation **avant** toute exécution ; écriture confinée ; n'enseigner que des hooks qui existent vraiment |
| P3 | Stockage | `ctx.store` + `versioned_kv` ; section `[storage]` lue ; migrations appelées ; fork via le registre (pas du cas par cas) ; harnais golden élargi (Facts, Timeline, événements, ChromaDB, fork en milieu de partie, config isolée) |
| P3 | Patches | Méthodes de classe et closures (ou refus explicite) ; ne pas lister comme actif un patch qui a échoué ; marquer `@patchable` les fonctions clés du moteur |
| P3 | Restes phase 0 | TICKET-102 côté Qt (rewind qui contourne `Session`), 103 (événements planifiés), 104 (regenerate), ids ChromaDB déterministes, auto-canonize hors des UI |
| P4 | Doc | Exemple de mod « canonique » qui marche (aujourd'hui faux dans 4 docs) ; README sans commandes inventées ; `ARCHITECTURE.md`, `AXIOM_STATUS.md`, `Changelog.md` mis à jour ; doublons `.en.md` à questionner |

## État réel (à la place des ✅ du TODO)

| Phase | Déclaré | Réel |
|---|---|---|
| 0 Assainir | ✅ | ~75 % : solide, mais fork living cassé, 2 rewinds (Qt), 103/104 ouverts, auto-canonize dans les UI |
| 1 Noyau | ✅ | Squelette correct ; ordre, versions, réversibilité, safe mode et stockage par politiques manquants |
| 2 Mods officiels | ✅ | Façade : les mods délèguent au code resté dans le noyau, et le noyau dépend des mods |
| 3 Patches | ✅ | Fonctions simples OK ; méthodes et closures KO ; aucun point `@patchable` dans le moteur |
| 4 Créateur | ✅ | Existe ; exécute avant confirmation ; génère des mods sur des hooks inexistants |
| 5 Store | ✅ | Code présent, catalogue absent, licence tranchée sans décision |

## Questions pour Frosoore
1. Le maintien d'`arbitrator.py` dans le noyau était-il une étape volontaire (ce qui devrait alors
   être écrit), ou pensais-tu la phase 2 finie ?
2. Les tests ont-ils été lancés sur ta machine avec des fichiers locaux dans `dist/mods/` ?
3. Qui a décidé la clause de licence et le passage du DOC en « FINALISÉE » ?
4. D-6 : qui est le propriétaire de `arbitrator.py` / `session.py` pour la suite ?
