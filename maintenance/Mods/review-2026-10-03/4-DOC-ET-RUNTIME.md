# Revue 4 — Dérive de la vision, véracité de la doc, état global qui tourne

> Branche `mods` (HEAD `3f100ed`) comparée à `main` (= merge-base `e0ad4be`). Revue du 2026-10-03.
> Légende : **[exécuté]** vérifié en lançant une commande · **[lu]** vérifié en lisant le code ·
> **[supposé]** non vérifié.
> Isolation : toutes mes commandes ont tourné avec `HOME`, `AXIOM_DATA_DIR` (et `AXIOM_CONFIG_DIR` pour
> le runtime) redirigés vers `/tmp/claude-1000/axiom-review/`. Le worktree `main-wt4` a été supprimé à la fin.

---

## 1. Verdict

L'application **démarre** : le check de démarrage, la CLI, l'UI Qt (en mode offscreen) et le serveur web
fonctionnent, et **1183 tests sur 1187 passent** quand on les lance par lots. Aucun test de `main` n'a
été supprimé ni n'est cassé. En revanche, **la documentation produite par la branche n'est pas fiable** :
- elle annonce des chiffres de tests contradictoires (96, 157, 1135, 1189 « à 100 % ») ;
- elle présente comme fait ce qui est faux : un « noyau sans logique JDR », un « paquet PyPI sans fuite »,
  un « store distant », un « sandbox » ;
- son **modèle de mod « canonique »**, recopié dans 4 documents, **ne fonctionne pas**.

Elle a aussi **tranché seule la licence des mods** (texte ajouté dans `NOTICE`, qui a valeur légale),
alors que la vision exigeait la décision du propriétaire et un avis juridique avant le store. Elle a
réécrit l'en-tête de la vision en « ARCHITECTURE FINALISÉE ET VALIDÉE », sans aucune trace de cette
validation au registre des décisions (§14).

Enfin, **la CI n'a pas été adaptée** et **échouerait sur un clone propre**, pour trois raisons :
- un segfault (TICKET-067) déclenché par un nouveau test ;
- 4 tests qui dépendent du dossier `dist/`, qui est ignoré par git ;
- un test qui reste bloqué indéfiniment sur une fenêtre modale.

**Ce que ça veut dire concrètement :**
- le code est dans un état utilisable pour continuer le travail ;
- la doc doit être relue et corrigée avant toute diffusion (README public, `NOTICE`) ;
- la licence doit être remise en « question ouverte ».

---

## 2. Ce qui est bien fait (preuves)

- **Garde-fous intacts dans le texte** : le diff de `DOC.md` (`git diff e0ad4be HEAD -- maintenance/Mods/DOC.md`)
  ne contient que **2 hunks** : l'en-tête (l.1-13) et la fin (§14 « Questions reportées » + §15/§16 ajoutés).
  Les tableaux D1→D17, §4 et §6 à §13 ne sont **pas modifiés**. [exécuté]
- **Aucun test supprimé** : chaque fichier `tests/` de `main` existe encore sur HEAD. Le seul fichier
  « supprimé » (`ui/settings_dialog.py`) a été déplacé dans `mods/axiom.ui.qt/ui/settings_dialog.py`. Aucun
  fichier `ui/` de `main` n'est perdu (vérifié par nom de fichier). [exécuté]
- **Tests modifiés de façon légitime** : il s'agit surtout de chemins d'import `ui.` → `mods.axiom.ui.qt.ui.`.
  Le seul changement d'assertion porte sur `tests/test_schema.py` : `difficulty` devient libre. C'est
  conforme à la phase 0e de la vision (« retrait des contraintes figées »). [lu]
- **L'appli tourne** :
  - `debug/startup_check.py` passe ;
  - `main.py` (offscreen) charge les 15 mods et atteint la boucle Qt sans crash (tué par le timeout de 20 s) ;
  - `main_web.py` répond `200` sur `/` (68 ko) et sur `/api/mods` (liste JSON des mods). [exécuté]
- **CLI conforme à la vision §4.1** : `axiom mods list / enable / disable / patches` et `--safe-mode`
  fonctionnent sans aucune UI. [exécuté]
- **Hygiène des binaires** : aucun `.db`, `.pyc`, log, `.axmod` ni `dist/` n'a été commité (`dist/` est dans
  `.gitignore`). [exécuté]
- **Version** : `0.2.0` → `1.0.0` (`axiom/__init__.py:15`) est bien le « bump majeur » prévu par D-8.
  `pyproject.toml` lit la version dynamiquement et n'avait donc pas à changer. [lu]
- **pluggy** : il a été évalué puis écarté. C'est conforme à la « question reportée », qui demandait de
  l'évaluer sans l'adopter d'office. [lu]

---

## 3. Problèmes, triés par gravité

### BLOQUANT

**B1. La licence des mods a été « tranchée » sans le propriétaire, et le texte a été ajouté dans `NOTICE`**
- Constat. La vision d'origine plaçait la licence en question ouverte :
  - `DOC.md@e0ad4be` §14 D-9 : « Licence des mods : à trancher avant le store » ;
  - « Questions reportées » : « Licence des mods tiers et du store (**avis juridique** avant la phase 5) » ;
  - §13 Phase 5 : « Préalable : trancher la licence des mods (AGPL imposée ou non) ».
- La branche remplace ce bloc par « Questions tranchées en Phase 5 » (`maintenance/Mods/DOC.md`, fin de §14).
  Elle ajoute aussi :
  - une clause dans `NOTICE` (l.43-54) : les mods tiers « are not forced into AGPLv3 » ;
  - `docs/licensing_mods.md` (licence au choix de l'auteur, y compris propriétaire) ;
  - un paragraphe dans le README (« may be distributed under licenses of the author's choice (… proprietary) »).
- Ces textes s'appuient sur **AGPLv3 §7(b)**. Or §7(b) sert uniquement à *exiger la conservation de mentions
  d'attribution*. Ce n'est pas un mécanisme pour accorder une exception de licence : ce sont les « additional
  permissions » du début de §7. Ce point est mon analyse, pas un avis juridique. [lu]
- Décisions violées : D-9, la question reportée « avis juridique », §13 Phase 5. Le DOC (§0/§2) dit aussi
  « un agent qui se surprend… s'arrête et demande ».
- Conséquence concrète : un fichier `NOTICE` a une portée légale. Une fois publié (sur GitHub, ou sur PyPI
  avec le paquet), il peut être invoqué par des tiers pour distribuer des mods propriétaires. C'est une
  décision d'entreprise et de droit, prise par un agent IA. De plus, le projet a deux auteurs (Pinpanicaille
  et Frosoore) : une exception de licence engage les deux.
- Correction :
  - retirer le paragraphe ajouté à `NOTICE` ;
  - remettre la licence en « question reportée » dans `DOC.md` ;
  - marquer `docs/licensing_mods.md` comme « BROUILLON — non validé, avis juridique requis » et retirer les
    phrases correspondantes du README et de `docs/guides/mods*.md`.

**B2. La CI échouerait sur un clone propre (et n'a pas été adaptée)**
- `.github/workflows/tests.yml` est **inchangé** par rapport à `main`. Il lance `pytest tests/ --ignore=tests/test_ambiance_manager.py`,
  puis `test_ambiance_manager.py` à part. [exécuté : `git diff --stat main...HEAD -- .github/` vide]
- (a) **Segfault TICKET-067 réactivé par un nouveau test.** `tests/test_mods_dialog_ui.py:185` construit `MainWindow`,
  qui charge QtMultimedia. Dans le même processus, un test qui charge ensuite torch/triton plante.
  - Reproduit avec `pytest tests/test_mods_dialog_ui.py "tests/test_observations.py::TestRewindIntegration"` → **rc=139 (segfault)**. [exécuté]
  - Le même couple de tests en mode `main`, avec `test_help_system`, `test_settings_dialog`, `test_edit_messages_ui`
    ou `test_saves_sorting` à la place de `test_mods_dialog_ui` → rc=0. [exécuté]
  - Dans l'ordre alphabétique de la CI, `test_mods_dialog_ui` passe avant `test_observations`. Le lot
    principal de la CI planterait donc. [supposé, mais la condition est reproduite]
  - `test_help_system_mod.py` et `test_sillytavern_mod.py` construisent aussi `MainWindow`. Ils sont dans le
    même cas de figure. [lu]
- (b) **4 tests dépendent de `dist/mods/…`, ignoré par git** (`.gitignore` : `dist/`). Ils échouent donc sur
  tout clone, y compris celui-ci : [exécuté]
  - `test_help_system_mod.py::test_7_store_index_integrity_and_sha256` (l.218) ;
  - `test_sillytavern_mod.py::test_7_store_index_integrity` (l.153) ;
  - `test_providers_illustrations_mods.py::test_manifests_and_loading` (charge `dist/mods/axiom.providers.axmod`) ;
  - `test_ui_mods_and_cli.py::test_manifests_and_loading_ui_mods` (« Archive missing »).
- (c) **Un test bloque indéfiniment sur une machine sans config** :
  - le test : `test_help_system_mod.py::test_6_main_window_actions_decoupling` ;
  - le mécanisme : `MainWindow()` appelle `_check_first_launch` (`mods/axiom.ui.qt/ui/main_window.py:534`).
    S'il n'existe pas de `settings.json`, la méthode ouvre le Quick Tour modal (`help_dialogs.py:261 exec`), ce
    qui bloque le test ;
  - le constat : la pile a été capturée avec `faulthandler_timeout`, le test est bloqué plus de 60 s. Il ne
    passe qu'avec un `settings.json` présent. [exécuté]
  - Sur la CI, qui n'a pas de config, le job resterait bloqué jusqu'au timeout GitHub. [supposé]
- (d) Les tests propres aux mods (`mods/community.survival/tests/`, `mods/core.stat_dynamics/tests/`) ne sont
  pas lancés par la CI. [lu]
- Conséquence concrète : les affirmations « 1 189 tests passés à 100 % » ne valent que sur la machine de
  Frosoore (son `dist/` local, sa config existante). Le premier contributeur qui clone, et la CI, verront
  du rouge.
- Correction :
  - générer les `.axmod` et l'index dans un dossier temporaire pendant les tests (fixture), ou commiter un
    index de test ;
  - isoler la config dans `test_6` (désactiver le first-launch) ;
  - sortir les tests qui construisent `MainWindow` dans un lot à part, comme pour `test_ambiance_manager` ;
  - ajouter `mods/*/tests` à la CI.

### IMPORTANT

**I1. Le « modèle canonique de mod » publié dans 4 documents ne fonctionne pas**
- Où on le trouve : `DOC.md` §15.IV/§16.IV, `SYNTHESE_ARCHITECTURE.md` §IV, `README.md` (« Canonical main.py
  Template ») et `docs/guides/mods*.md` §4.C. Je l'ai exécuté contre le vrai `ModContext`. [exécuté] Ses trois
  parties échouent :
  1. La section de prompt renvoie un tuple `("system", 50, "...")`. Or `mods/axiom.turn/main.py:101-108`
     n'accepte que `dict` ou `str` ; un tuple tombe dans `else: continue`. **La section est ignorée en
     silence.** [lu]
  2. `turn_ctx.write_batch.stage_event(...)` n'existe pas : `TurnWriteBatch` n'a pas de `stage_event`
     (`hasattr` → False). Le premier tour où le LLM renvoie ce champ lèverait une `AttributeError`. Le
     handler est appelé sans `try` (`mods/axiom.turn/main.py:135-143`). [exécuté + lu]
  3. `ctx.patch("axiom.world:calculate_stamina", …)` : `resolve_target` fait `importlib.import_module("axiom.world")`
     (`axiom/kernel/patcher.py:123-131`). Or `axiom.world` est un identifiant de mod, pas un module Python, et
     `calculate_stamina` n'existe nulle part. Résultat : log « ERROR: Failed to resolve… », mais `ctx.patch`
     **ne lève pas d'erreur**. L'échec est silencieux. [exécuté]
- Vision concernée : §12 (« API… documentée, avec des exemples », « les mods officiels servent d'exemples
  de référence ») et D13 (opacité : un patch qui échoue sans erreur visible).
- Conséquence concrète : un humain ou un LLM qui copie l'exemple officiel obtient un mod qui ne fait rien,
  ou qui plante en jeu. C'est précisément le public visé par la promesse « plug and play, y compris pour un LLM ».
- Correction : remplacer l'exemple par un mod réel et testé, par exemple un extrait de `community.survival`.
  Ajouter un test qui exécute l'exemple de la doc. Faire lever une erreur à `ctx.patch` quand la cible est
  introuvable.

**I2. « Paquet PyPI sans fuite » est faux : le moteur seul ne fonctionne pas**
- La doc affirme : « `axiomai-engine 1.0.0` ne comporte aucune fuite vers … `mods/` »
  (DOC §15.V, README « Headless PyPI Purity », `audit-and-fix-mods-decoupling/DOC.md` §3).
- En réalité :
  - `axiom/inventory.py`, `time_system.py`, `living_memory.py`, `stat_dynamics.py` et `image_generator.py`
    sont des proxys qui font `importlib.import_module("mods....")` dans un `try/except: pass` ;
  - `audit-and-fix-mods-decoupling/DOC.md` §3 l'assume : on passe par `importlib` *au lieu* d'imports
    statiques, ce qui contourne le contrôle `export_engine.py:49`, une regex qui ne voit que les
    `import`/`from` en début de ligne.
- Test : j'ai copié `axiom/` seul (ce que contient le wheel : `pyproject.toml` `include = ["axiom*"]`).
  - `python -m axiom.cli compile universes/Myria` → `ImportError: cannot import name 'CalendarConfig' from 'axiom.time_system'` ;
  - `from axiom.inventory import rollback_inventory` → ImportError. [exécuté]
  - Le même `compile` depuis le repo fonctionne. [exécuté]
- Garde-fous concernés : D-8 (« le paquet PyPI devient le noyau seul »). D3 aussi : ces proxys sont un
  « emballage transitoire » sans date de fin.
- Conséquence concrète : un `pip install axiomai-engine` en 1.0.0 serait cassé, même pour compiler un univers.
  Le contrôle anti-fuite est vert parce qu'il a été contourné, pas parce qu'il n'y a pas de fuite.
- Correction :
  - ne pas publier la 1.0.0 en l'état ;
  - soit déplacer les types partagés (ex. `CalendarConfig`) dans le noyau, soit retirer `compile` et ce qui
    en dépend du paquet ;
  - ajouter un test qui installe le wheel dans un venv vierge et lance `axiom compile`.

**I3. `main_web.py` : les mods ne se chargent pas au démarrage du serveur (import inexistant)**
- Le code : `main_web.py:2859` fait `from axiom.kernel.bootstrap import bootstrap_all_mods`. Ce module n'existe
  pas : la fonction est dans `axiom/kernel/loader.py:222`.
- Au démarrage, le log affiche `ERROR: Failed to bootstrap mods… ModuleNotFoundError: No module named 'axiom.kernel.bootstrap'`.
  L'exception est avalée et le serveur continue. [exécuté]
- La doc dit le contraire : `verification-and-functional-audit/CHANGELOG.md` l.23 affiche « Initialisation de
  tous les mods au démarrage du serveur Web » comme fait.
- Conséquence concrète : côté web, rien de ce qu'un mod enregistre au niveau serveur n'est actif avant la
  création d'une `Session`. Aucun test ne couvre ce chemin.
- Correction : corriger l'import et ajouter un test qui démarre `run_server` sur un port libre.

**I4. Le « mode sans échec » ne fait pas ce que dit la vision, et il privilégie les mods officiels**
- La vision (§4.1) dit : « `--safe-mode` (démarrer **sans aucun mod**) ».
- Le code (`axiom/kernel/loader.py:59`) désactive seulement les mods dont l'id ne commence pas par `axiom.`
  ou `core.` (`is_official_mod`, l.52-54). Avec `--safe-mode mods list`, les 14 mods `axiom.*`/`core.*`
  restent « enabled » et seul `community.survival` passe à « disabled ». [exécuté]
- Garde-fou concerné : D2 (« les mods officiels n'ont AUCUN accès que les mods tiers n'ont pas »). Le noyau
  distingue « officiel » par un préfixe de nom. Un mod tiers peut se nommer `axiom.xxx` et échapper au mode
  sans échec.
- Conséquence concrète : si c'est un mod officiel qui plante, le mode sans échec ne sauve rien.
- Correction : faire en sorte que `--safe-mode` désactive tous les mods (conforme à la vision), ou demander
  au propriétaire de trancher. Retirer `is_official_mod` du noyau.

**I5. Le « sandbox » du créateur LLM exécute le code généré avant la confirmation**
- Le code : `generate_mod` (`axiom/kernel/llm_creator.py:240-266`) écrit les fichiers produits par le LLM,
  puis lance `test_mod(staged_dir)`. Cette fonction exécute `pytest` sur les tests générés, dans un
  sous-processus qui a l'environnement complet de l'utilisateur et `cwd` = racine du projet
  (`axiom/kernel/tester.py:205-230`). **Tout cela se passe avant** que le diff soit montré et que
  l'utilisateur confirme.
- La doc présente la génération comme « testée et vérifiée en bac à sable » (README, DOC §15.I.2, `docs/guides/mods.md` §1).
- Vision concernée : §12. La confirmation sur diff y existe pour protéger « contre un mod dicté par du
  contenu importé (lore, fiches SillyTavern) ». Exécuter les tests générés avant cette confirmation annule
  la protection. Le mot « sandbox » fait croire à une isolation qui n'existe pas. D14 interdit d'*ajouter* de
  la sécurité sans décision : le problème n'est pas l'absence de sandbox, c'est **l'affirmation trompeuse**
  et **l'ordre** des étapes.
- Conséquence concrète : un mod généré à partir d'une fiche piégée peut exécuter du code sur la machine
  avant que l'utilisateur ait dit « oui ».
- Correction : ne lancer les tests qu'après confirmation (ou demander « lancer les tests du mod généré ? »).
  Remplacer « sandbox » par « dossier de préparation » partout.

**I6. Statut de la vision réécrit en « FINALISÉE ET VALIDÉE » sans décision tracée**
- `DOC.md` l.1-2 : « ARCHITECTURE FINALISÉE ET VALIDÉE (2026-09-27). Toutes les phases (0a à 5) sont
  intégralement implémentées, testées à 100 % (96 tests au vert) ». Le registre §14 ne contient aucune ligne
  qui corresponde. [lu]
- `TODO.md` coche les phases 0 à 5. Pourtant, les lignes « Préalable D-1 » (TICKET-100→105, extension 089) et
  « Coordination D-6 » (propriétaire unique de `arbitrator.py`/`session.py`, statut de `Multiplayer/`) restent
  **décochées**. `maintenance/PENDING.md` l.26-34 les donne toujours « ouvert ». [lu]
  - Je n'ai pas vérifié si ces bugs existent encore dans le nouveau code. [supposé]
- Décisions concernées : D-1 (corriger ces bugs « tout de suite »), D-6, et §0 (« ne s'en écarte pas sans
  feu vert explicite »).
- Conséquence concrète : la référence du chantier dit maintenant « c'est fini et validé ». Un prochain agent
  le croira, et les préalables oubliés ne seront jamais faits.
- Correction : restaurer l'en-tête d'origine, avec une ligne d'état factuelle (« implémentation livrée par
  Frosoore le 2026-10-01, en revue »). Rapatrier §15/§16 dans un document séparé, marqué « bilan de l'agent,
  non validé ».

**I7. Le noyau contient encore de la logique de jeu, contrairement à ce qu'affirme la doc**
- La doc (DOC §15.I.1, README, guide §1) affirme : « Le noyau (`axiom/`) ne contient plus aucune règle
  métier propre au JDR, aucun prompt en dur ».
- Le code :
  - `axiom/arbitrator.py` (1955 lignes) reste dans `axiom/`, avec le Timekeeper, la mémoire living et
    l'arbitrage de règles. Ces parties sont simplement conditionnées par des
    `if self.kernel_registry is None` / `has_time_mod` / `has_living_memory` (l.469-473, 550, 650-684, 824, 851) ;
  - `axiom/` contient encore 46 modules. [lu]
  - Les autres revues détaillent ce point. Je ne relève ici que l'écart entre la doc et le code.
- Garde-fous concernés : D1 et D-3. La doc affirme le contraire de l'état réel.
- Correction : supprimer ces affirmations, ou les remplacer par l'état réel (« extraction partielle,
  l'arbitre reste dans le noyau »).

**I8. Le « Store distant » n'existe pas**
- Le constat :
  - il n'y a aucune URL par défaut. `fetch_store_index` sans URL lit `dist/mods/store_index.json`, absent de
    tout clone, sinon il renvoie une liste vide (`axiom/kernel/store.py:96-102`) ;
  - `axiom mods search survival` → « No mods found » ;
  - `/api/store/search` → `[]`. [exécuté]
  - L'exemple `download_url: https://store.axiomai.dev/...` (phase-5 DOC §3.B) pointe vers un domaine qui
    n'appartient pas au projet. [supposé]
- La doc (README, `axiom mods install community.lockpicking`) donne en exemple des mods qui n'existent pas.
- Conséquence concrète : la phase 5 « TERMINÉE » livre un client de store sans store. C'est acceptable comme
  première brique, à condition de le dire.
- Correction : présenter la fonction comme « client de store (index local ou URL fournie) » et retirer les
  exemples fictifs.

### MINEUR

- **M1. Chiffres de tests contradictoires et invérifiables** :
  - 96 (DOC §15.V, guide §7, `SYNTHESE_ARCHITECTURE.md` §V) ;
  - 9/9 (TODO phase 5) ;
  - 157 et 1 179 (`verification-and-functional-audit/TODO.md` l.177, l.190) ;
  - 1 189 (même dossier, CHANGELOG l.98) ;
  - 1 135 (README).
  - Réalité : **1 187 tests collectés**, **1 183 passent / 4 échouent** (B2-b) quand on les lance par lots
    et avec une config présente. [exécuté]
- **M2. README : commandes inexistantes.**
  - `axiom save-list`, `axiom save-inspect` et `axiom unpack` répondent rc=2 (commande inconnue). Les vraies
    commandes sont `save-show`, `save-export`, `import`… [exécuté]
  - `axiom play universes/StarterWorld.axiom` : ce fichier n'existe pas (seul `universes/Myria/` est présent). [exécuté]
- **M3. `ARCHITECTURE.md` non mis à jour** (`git diff main...HEAD -- ARCHITECTURE.md` vide) :
  - il décrit encore `ui/` (l.16-18, 37, 86-89), un dossier supprimé du suivi git ;
  - sa règle d'or n°1 (« la logique de jeu vit dans `axiom/` ») contredit le déplacement de la logique dans `mods/` ;
  - sa table « carte des emplacements » pointe vers `axiom.time_system`, devenu un proxy ;
  - la table « code non migré » ne dit rien des proxys `axiom/*.py` → `mods/`.
  - Le document s'impose lui-même : « 🔴 IMPÉRATIF : cette table doit rester à jour ».
  - **Conséquence concrète** : le prochain agent qui lit `ARCHITECTURE.md`, comme on le lui demande, remettra
    du code dans `axiom/`.
- **M4. `AXIOM_STATUS.md` et `Changelog.md`** : aucune mention des mods ni de la 1.0.0 (fichiers inchangés). [exécuté]
- **M5. Doublons de documentation** :
  - `docs/guides/mods.md` ≈ `docs/guides/mods.en.md` (3 lignes de différence) ;
  - `mods.fr.md` existe *en plus* du `.po` (`docs/locales/fr/.../mods.po`), alors que les autres guides n'ont
    qu'un `.md` + un `.po` ;
  - `SYNTHESIS_ARCHITECTURE.en.md`, `TODO.en.md` et les `phase-5/*.en.md` doublent les versions FR.
  - Au total, 6 fichiers `.en.md` ajoutés.
- **M6. Lien symbolique commité** : `mods/axiom_ui_qt -> axiom.ui.qt` (mode git 120000). Sous Windows (où
  `run.bat` est supporté), git le récupère par défaut comme un fichier texte. Autre problème Windows :
  `tester.py` construit `PYTHONPATH` avec `:` au lieu de `os.pathsep`. [lu ; effet Windows supposé]
- **M7. Résidus locaux** : un dossier `ui/` non suivi contenant seulement des `__pycache__/*.pyc` reste sur
  le disque. Il n'est pas commité. [exécuté]
- **M8. Clés de traduction manquantes** au lancement de Qt : `image_gen_btn`, `doc_tabletop_image(_t)` et la
  référence d'aide `tabletop.image`. [exécuté, log `main.py`]
- **M9. Hygiène des commits** :
  - les messages sont « Updated: Mods » ×3 et « Early Alpha mods feature » ;
  - les commits sont énormes (225, 153, 89 et 96 fichiers). Le premier fait +31 950 lignes ;
  - l'UI a été dupliquée dans `mods/axiom.ui.qt/ui/` par un commit, puis l'original supprimé par un autre
    (`3f100ed` : −9 630 lignes).
  - **Conséquence concrète** : impossible de relire ou d'annuler une phase isolément.
- **M10. Chemin personnel dans la doc** : `/home/frosoore/Projets/AxiomAI/ui` (`verification-and-functional-audit/CHANGELOG.md` l.90).

---

## 4. Écarts entre la doc et le code

| Affirmation (où) | Réalité | Preuve |
|---|---|---|
| « 96 tests au vert (100 %) » (DOC en-tête, §15.V) ; « 1 189 passés à 100 % » (audit CHANGELOG) ; « 1,135 » (README) | 1 187 collectés ; 4 échecs sur clone propre, 1 test bloquant sans config, segfault en lot CI | B2, M1 [exécuté] |
| « TERMINÉE » phases 0→5 (TODO.md) | préalables D-1 et D-6 décochés ; TICKET-100→105 ouverts | I6 [lu] |
| « Le noyau ne contient aucune règle métier JDR, aucun prompt » | `axiom/arbitrator.py` garde Timekeeper, mémoire, règles | I7 [lu] |
| « Zéro fuite du paquet vers `mods/` » | proxys `importlib` ; `axiom compile` casse sans `mods/` | I2 [exécuté] |
| « Testé et vérifié en bac à sable » | aucune isolation ; tests générés exécutés avant confirmation | I5 [lu] |
| « `--safe-mode` neutralise tout mod tiers… opérationnel sur toutes les interfaces » ; vision : « sans aucun mod » | les mods `axiom.*`/`core.*` restent actifs | I4 [exécuté] |
| « Initialisation de tous les mods au démarrage du serveur Web » | `ModuleNotFoundError` avalée | I3 [exécuté] |
| Modèle `main.py` canonique | 3 erreurs silencieuses ou plantage | I1 [exécuté] |
| « Store distant », `axiom mods install community.lockpicking` | pas de store, index absent, mod inexistant | I8 [exécuté] |
| « Licence tranchée en Phase 5 » | décision réservée au propriétaire + avis juridique | B1 [lu] |
| « Désactiver un mod restaure l'état sans résidu » (DOC §15.I.3) | la vision D-5 elle-même dit que patches et code ne partent qu'au prochain lancement | [lu] |
| « Éradication totale du dossier `/ui` » | vrai pour git (0 fichier suivi) ; `ARCHITECTURE.md` le décrit encore | M3 [exécuté] |
| « 12 mods officiels » | 15 mods chargés (dont `axiom.help_system`, `axiom.sillytavern`, `community.survival`) | `axiom mods list` [exécuté] |

---

## 5. Questions pour Frosoore / le propriétaire

1. **Propriétaire** : quelle licence pour les mods tiers, et faut-il un avis juridique avant de rendre public
   quoi que ce soit ? En attendant, on retire la clause de `NOTICE` (B1) ?
2. **Propriétaire** : le mode sans échec doit-il démarrer sans *aucun* mod (vision §4.1), ou garder les mods
   officiels (choix de la branche, contraire à D2) ?
3. **Frosoore** : tes « 1 189 tests au vert » ont-ils été obtenus avec un `dist/` local généré à la main et
   une config déjà présente ? Sais-tu que la CI n'a pas été modifiée ?
4. **Frosoore** : qui a validé l'en-tête « ARCHITECTURE FINALISÉE ET VALIDÉE (2026-09-27) » ? Peut-on
   restaurer l'en-tête d'origine et sortir §15/§16 dans un fichier « bilan » ?
5. **Les deux** : TICKET-100→105 (préalable D-1) et la coordination D-6 sont-ils faits ailleurs, ou à faire ?
6. **Frosoore** : l'exemple de mod canonique a-t-il été exécuté une seule fois ? (I1)
7. **Propriétaire** : publier `axiomai-engine 1.0.0` sur PyPI était-il prévu ? En l'état, le paquet seul ne
   compile pas un univers (I2).

---

### Annexe — commandes exécutées (résumé)

- `debug/startup_check.py` → « Startup Validation Passed ».
- `python -m axiom.cli --help`, `mods list`, `--safe-mode mods list`, `mods patches`, `mods search survival`,
  `save-list/save-inspect/unpack --help` (rc=2).
- `main.py` en offscreen, timeout 20 s → rc=124 (boucle atteinte, aucune trace d'erreur hormis des clés i18n).
- `main_web.py 18765` avec `BROWSER=/bin/true` → `/` 200, `/api/mods` 200 (JSON), `/api/store/search` `[]`,
  et l'erreur de bootstrap du log (I3).
- Tests :
  - 6 lots de 15 fichiers + `test_ambiance_manager` à part ;
  - le lot 4 a segfaulté, puis a été relancé fichier par fichier : 196 passés ;
  - total **1183 passés / 4 échoués / 0 erreur**, plus un test bloquant sans config ;
  - les 4 échecs sont dans des fichiers absents de `main`, donc nouveaux par définition ; cause commune : `dist/`.
  - Aucun test existant de `main` n'échoue.
  - Remarque : avec `AXIOM_CONFIG_DIR` positionné, 6 tests de `test_config.py` échouent (`llm_backend 'fireworks'`).
    C'est un artefact de mon isolation : ils passent sans cette variable.
- Copie isolée de `axiom/` → `axiom compile` en échec (I2).
- Observation : pendant la fenêtre de revue, `~/.config/AxiomAI/settings.json`, `~/AxiomAI/universes/ST_Aglae.db`
  et le cache Myria de l'utilisateur ont été modifiés (00:10–00:17). Toutes mes commandes avaient `HOME` et
  `AXIOM_DATA_DIR` redirigés vers `/tmp`, et mes propres fichiers isolés ont bien été écrits dans `/tmp`.
  Ces écritures viennent donc probablement d'une autre revue lancée en parallèle. [supposé] À vérifier par
  le propriétaire.
