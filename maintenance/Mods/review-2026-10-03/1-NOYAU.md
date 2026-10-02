# Revue 1 — LE NOYAU (phases 1, 3, 4, 5)

Périmètre : `axiom/kernel/*` (loader, manifest, registry, resolver, context, step_context, patcher,
scaffold, tester, dev, llm_creator, store, dependencies, `__init__`), `axiom/cli/mods_cmd.py`,
`axiom/cli/test.py`, `mods/__init__.py`. Référence : `git show e0ad4be:maintenance/Mods/DOC.md`
(§2, §4, §5, §6, §7, §8, §10.5, §12, §13, §14). Branche `mods` @ `3f100ed`.

Légende des preuves : **[exécuté]** = vérifié en lançant du code (scripts dans
`/tmp/claude-1000/axiom-review/`) ; **[lu]** = vérifié en lisant le code ; **[supposé]** = déduction
non vérifiée.

---

## 1. Verdict

Le noyau existe, il est petit (≈3 900 lignes) et lisible. Le parseur de manifeste, le tri des
dépendances et les trampolines `@patchable` sont corrects sur les cas simples, et 71 tests sur 72
passent. **Mais plusieurs promesses centrales de la vision ne sont pas tenues, alors que le TODO
les coche toutes :**

- **un seul conflit ou un seul cycle entre mods empêche le chargement de TOUS les mods**, y compris
  le tour de jeu. Le jeu devient inutilisable et l'utilisateur ne voit qu'une ligne de log ;
- la **profondeur** (§1.3, D8) n'est pas tenue : les patches **ne marchent pas sur les méthodes de
  classe ni sur les closures**. Ils échouent sans rien dire mais sont listés comme « actifs ».
  Aucune fonction du moteur n'est marquée `@patchable` ;
- la **réversibilité** (D11) et l'**activation à chaud** (D-5) sont simulées : personne n'appelle
  `ctx.cleanup()` en production. Activer ou désactiver un mod relance le code de *tous* les mods
  dans un nouveau registre, et la partie en cours garde l'ancien ;
- le noyau **connaît les LLM et le JDR** (D1) : il importe la config applicative (clés API,
  modèles…), `axiom.backends` et un créateur LLM, et son contexte de step contient `llm`,
  `time_llm`, `vector_memory`, `hero_entity_id` ;
- le **créateur LLM exécute le code généré AVANT la confirmation** de l'utilisateur et peut écrire
  hors du dossier de préparation. Cela annule la seule protection que §12 prévoyait ;
- le **store** a été construit malgré le préalable de §13 (licence et installeur pip à trancher
  d'abord). Son catalogue n'existe pas dans le repo (`dist/` est ignoré par git).

Le travail est une **bonne base de prototype** mais pas un noyau « phase 1 à 5 terminées ». Il ne
faut pas le fusionner en l'état comme fondation définitive.

---

## 2. Ce qui est bien fait (preuves)

| Point | Preuve |
|---|---|
| Manifeste strict : id namespacé `auteur.nom` obligatoire, SemVer, `axiom_api` entier ≥ 1, lecture TOML sans exécuter de code, UTF‑8 explicite partout | `manifest.py:24-25,152-183,270` [lu] ; tests `test_kernel_loader` [exécuté] |
| `.axmod` = zip : lecture du manifeste et des locales dans l'archive, chargement de `main.py` depuis l'archive sans extraction | `manifest.py:297-340`, `loader.py:138-205` ; un mod mono-fichier se charge depuis une archive [exécuté] |
| Résolveur : tri topologique déterministe, cycle détecté **avec son chemin** (`a.a -> b.b -> a.a`), suppression en cascade des mods dont une dépendance obligatoire manque, avec la raison, ids virtuels `provides`, contraintes `before/after` respectées même contre l'ordre utilisateur | `resolver.py:69-192` ; `t_resolver.py` [exécuté] |
| Isolation des plantages de hooks : une exception est journalisée, les autres hooks tournent, le step continue | `registry.py:79-103` ; `t_ws.py` [exécuté] |
| **D10 respecté** : un mod peut créer ses emplacements (`[provides_slots]` + `ctx.declare_slot`) et les mods d'UI le font (`axiom.ui.web:side_panel`, `axiom.ui.qt:sidebar_widget`, `axiom.ui.qt:settings_tab`…) | `loader.py:99-104`, `context.py:51-56` ; grep des `get_slot` [lu] |
| Trampolines `@patchable` : before/after/around + `ShortCircuit`, **les `from x import f` capturés voient le patch**, empilement de deux mods, retrait propre par mod | `patcher.py:87-104,264-314` ; `t_patch.py` cas 1-3 [exécuté] |
| Secours `__code__` sur fonction de module ordinaire : identité de l'objet conservée, from-import capturé patché, bytecode d'origine restauré au retrait | `patcher.py:170-192,231-251` ; `t_patch.py` cas 4 [exécuté] |
| Pile de patches figée pendant un step (`PatchingDuringStepError`), branchée dans `axiom.turn` | `patcher.py:76-84,151-156` ; `mods/axiom.turn/main.py:34` ; `t_patch.py` cas 9 [exécuté] |
| CLI utilisable **sans aucune UI** : `axiom mods list/enable/disable/patches/validate/pack/new/test/dev/generate/search/install/update`, `--safe-mode` | `mods_cmd.py:97-202`, `axiom/cli/main.py:58,154` ; `mods list` lancé en terminal [exécuté] |
| Créateur LLM : vrai appel LLM (backend de la config), diff unifié coloré, confirmation `[y/N]` en CLI | `llm_creator.py:213-225`, `mods_cmd.py:438-461` [lu] |
| D-7 respecté au sens strict : **aucun installeur pip**, seulement une vérification de `[python].requires` | `dependencies.py` entier [lu] |
| Store : vérification SHA‑256 de l'archive téléchargée | `store.py:246-255` [lu] |

---

## 3. Problèmes, triés par gravité

### BLOQUANT

#### B1. Un seul conflit ou un seul cycle désactive TOUS les mods, sans message visible
- **Constat** : `resolve_load_order` **lève une exception** (`ConflictError`, `CyclicDependencyError`)
  au lieu d'écarter les mods fautifs (`resolver.py:91-97,163-167`). `bootstrap_all_mods`
  l'attrape, journalise une erreur et **renvoie un registre vide** (`loader.py:252-256`).
- **Preuve [exécuté]** : avec un mod `f.conflict` qui déclare `conflicts=["b.backend"]`, on obtient
  `services after conflict: []`. Aucun mod n'est chargé.
- **Violé** : §4.1 (« isole les plantages »), §8 (« la liste affiche les conflits »), D13.
- **Concrètement** : un seul mod tiers mal écrit (ou deux mods incompatibles) supprime le tour de
  jeu, la mémoire, les providers… La prochaine partie échoue avec « No turn pipeline installed »,
  sans expliquer pourquoi.
- **Correction** : le résolveur **écarte** les mods en conflit ou pris dans un cycle (avec une
  raison dans `report.disabled_mods`) et charge le reste. Le bootstrap affiche ce rapport (CLI,
  UI, log).

#### B2. Les patches ne marchent ni sur les méthodes ni sur les closures, et le système affirme le contraire
- **Constat** : `resolve_target` découpe la cible `module.fonction` sur le dernier point
  (`patcher.py:123-137`). `tgt.C.meth` donne donc le module `tgt.C`, qui n'existe pas. L'erreur
  est **avalée** (`patcher.py:193-194`) mais l'enregistrement est **quand même ajouté** à la pile
  active (`patcher.py:196-197`). Pour une closure, l'affectation de `__code__` échoue (le code du
  trampoline n'a pas de variables libres) et ça se termine de la même façon.
- **Preuve [exécuté]** (`t_patch.py`) :
  `5 closure patched call: 6 (expect -1)` puis `active patches listed: [('m.a','tgt.closed')]` ;
  `6 method: 4 (expect 999)` puis `listed as active: ['tgt.C.meth']`. La syntaxe `tgt:C.meth` échoue aussi.
- **Aggravant [lu]** : **aucune** fonction du moteur n'est marquée `@patchable` (grep : 0 résultat
  hors `patcher.py`). Or le cœur du jeu est fait de méthodes (`Session.take_turn`, `ArbitratorEngine.*`).
- **Violé** : §1.3 / D8 (profondeur non négociable), §6.2 point 2, D13 (`axiom mods patches`
  affiche des patches qui n'agissent pas).
- **Concrètement** : un moddeur ne peut pas modifier le tour de jeu par patch, et l'outil lui dit
  que son patch est actif alors que rien ne se passe.
- **Correction** : résoudre les cibles `module:Classe.méthode` (getattr en chaîne) et patcher la
  méthode via `__code__` ou un remplacement sur la classe. Refuser bruyamment (exception, rien
  dans la pile) toute cible non patchable. Marquer `@patchable` les points chauds du tour.

### IMPORTANT

#### I1. D1 violé : le noyau connaît les LLM, la config applicative et le JDR
- **Constats [lu]** :
  - `registry.py:13` importe `axiom.backends.base.GenerationCancelled` (une notion LLM) ;
  - `context.py:12`, `loader.py:16`, `dev.py:19` et `store.py:21` importent `axiom.config.AppConfig`,
    la config de l'application (clés Gemini/OpenAI/Anthropic, modèles, Timekeeper, images…,
    `config.py:44-197`). `manifest.py:87,125` lit la langue de l'app ;
  - `step_context.py:17-38` : le « step générique » de D-3 contient `llm`, `time_llm`,
    `vector_memory`, `hero_entity_id`, `verbosity_level`, `temperature`, `top_p`, `mode` ;
  - `llm_creator.py:18-19` (dans le noyau) importe `LLMBackend` et `build_llm_from_config` ;
  - les emplacements `axiom.kernel:locales` / `axiom.kernel:help_entries` sont déclarés **par le
    noyau** (`registry.py:57-58`), alors que §9 les place dans les mods d'UI.
- **[exécuté]** : `import axiom.kernel` charge `axiom.backends`, `axiom.backends.base`,
  `axiom.config` et `mods` (21 modules).
- **Pas de violation constatée** dans l'autre sens : le noyau n'importe aucun mod de jeu, et aucun
  `if mod_id == "axiom.turn"` n'a été trouvé.
- **Concrètement** : le « noyau seul » publiable sur PyPI (D-8) n'existe pas. Le paquet `axiom*`
  embarque tout le moteur de JDR (`arbitrator.py` fait 1 955 lignes, `mods/axiom.turn/main.py`
  177 lignes qui l'appellent).
- **Correction** : sortir `llm_creator` du noyau (en faire un mod). Remplacer `GenerationCancelled`
  par une exception propre au noyau (ex. `StepAborted`) que le backend dérive. Donner à
  `ModContext` une config par mod indépendante d'`AppConfig`. Réduire `KernelStepContext` à
  `save_id/step/epoch/input/payload: dict`.

#### I2. Les exceptions du tour sont avalées : la vraie erreur est perdue
- **Constat [lu]** : `Session.take_turn` lance le tour par `execute_hook("axiom.kernel:execute_step")`
  (`session.py:335`). Or `invoke_hook` **avale toute exception** sauf `GenerationCancelled`
  (`registry.py:93-102`). Ensuite `session.py:337-338` lève `RuntimeError("Turn pipeline mod
  returned no result.")`.
- **Concrètement** : une clé API invalide, un quota dépassé (429) ou une erreur SQL deviennent tous
  le même message vague. L'utilisateur et le support ne savent plus ce qui a cassé.
- Un « tour » n'est pas un hook à collecter : c'est un **emplacement exclusif**. Deux mods qui
  s'enregistrent sur `execute_step` s'exécutent l'un après l'autre (`registry.py:89`).
- **Correction** : faire de `execute_step` un emplacement exclusif appelé sans filet, ou bien
  conserver l'exception et la relever.

#### I3. La réversibilité (D11) et l'activation à chaud (D-5) ne sont pas réelles
- **Constats [lu]** :
  - `ctx.cleanup()` n'est appelé **que** par `dev.py`, `tester.py` et `scaffold.py` (grep). Le
    loader ne garde aucune référence aux `ModContext` (`loader.py:258-264`). On ne peut donc pas
    retirer *un* mod ;
  - le bouton activer/désactiver de l'UI Qt crée un **nouveau registre** et relance
    `bootstrap_all_mods`, ce qui **ré-exécute le `main.py` de tous les mods**
    (`mods/axiom.ui.qt/ui/mods_dialog.py:520-534`). Or D-5 dit « code arbitraire : au prochain
    lancement » ;
  - la `Session` en cours garde l'ancien registre : personne n'utilise le setter
    `session.kernel_registry` (`session.py:277-281` ; grep sans appelant) **[supposé : la partie
    en cours ne voit pas le changement]** ;
  - chaque `Session()` construite sans registre relance tout le bootstrap (`session.py:156-158`),
    en plus de `main.py:436` et `main_window.py:80-82`. **[exécuté]** : deux bootstraps donnent
    deux registres distincts, et tous les `main.py` s'exécutent deux fois ;
  - `main_web.py:2859` importe `axiom.kernel.bootstrap`, **qui n'existe pas**. L'`ImportError`
    est avalée (`except Exception`), donc le serveur web démarre sans bootstrap et ce sont les
    `Session` qui le font ensuite.
  - `ModContext` ne gère ni threads/jobs de fond, ni époques, ni stockage de save (`ctx.store`),
    ni traductions, alors que §5.3 et §10.4 l'exigent (`context.py:36-39`). Les mods lancent leurs
    threads eux-mêmes : `mods/axiom.illustrations/main.py:133`,
    `mods/axiom.living_memory/living_memory.py:577`, `mods/axiom.ui.web/main.py:62`.
  - `ModContext.cleanup` ne retire pas les emplacements que le mod a **déclarés**
    (`context.py:51-56,79-94`).
- **Concrètement** : désactiver un mod n'arrête pas ses threads. Activer ou désactiver relance tout
  le code. La partie en cours peut continuer avec l'ancien état.
- **Correction** : le loader garde `{mod_id: ModContext}`. Désactivation à chaud = `ctx.cleanup()`
  du mod concerné **si** il n'a ni patch ni code « brut » ; sinon on affiche « au prochain
  lancement ». Ajouter `ctx.spawn_job()` (avec capture d'époque), `ctx.store`, `ctx.config` propre.
  Un seul bootstrap par processus (D-4).

#### I4. Un hook qui plante ne désactive pas son mod, et un `init()` raté laisse des restes
- **Preuves [exécuté]** (`t_ws.py`) :
  - le hook de `a.backend` lève `ZeroDivisionError` à chaque appel. Il reste enregistré et il est
    rappelé à chaque step (`a.backend still registered: True`). Les autres hooks du même mod
    continuent de tourner ;
  - `c.partial` enregistre un hook puis lève une erreur dans `init()`. `ModLoadError` est bien
    levée, mais **le hook reste actif** (`invoke k:h -> [..., 'C partial registered']`) ;
  - `e.dependent` dépend de `c.partial` (qui a échoué) : il est **chargé quand même**.
- **Violé** : §6.1 (« le mod est désactivé et signalé »), D11.
- **Correction** : en cas d'exception dans un hook ou dans `init`, appeler `ctx.cleanup()`, marquer
  le mod comme désactivé avec sa raison, puis écarter ses dépendants.

#### I5. Versions d'API et versions de dépendances jamais vérifiées (D12)
- **Preuves [exécuté]** :
  - `axiom_api=99` : le mod est résolu et **chargé** (`d.futureapi` → service `future` présent) ;
  - `"b.b" = ">=2.0"` alors que `b.b` est en 1.0.0 : chargé sans avertissement ;
  - `"b.b" = "n importe quoi"` : accepté.
- **[lu]** : `version_spec` n'est lu nulle part dans `resolver.py`. `axiom_api` n'est comparé
  qu'à l'affichage (`mods_cmd.py:293`) et dans le store, en dur à `1` (`store.py:259`).
- **Concrètement** : la logique « versions Minecraft » n'existe pas. Un mod fait pour une autre
  API se charge puis casse à l'exécution.
- **Correction** : constante `KERNEL_API = 1` dans le noyau ; écarter avec une raison tout mod où
  `axiom_api != KERNEL_API` ; vérifier les specs avec `packaging.specifiers`.

#### I6. Pas d'ordre utilisateur et conflits d'emplacements invisibles (§8, D13)
- **[lu]** : `resolve_load_order(manifest_map)` est appelé **sans** `user_order`
  (`loader.py:253`) et aucune config ne stocke d'ordre (grep `user_order|load_order`). L'ordre
  réel est **alphabétique** sous contraintes.
- **[exécuté]** : sur un emplacement exclusif, le second contributeur reçoit `RegistryError`. Son
  `init()` entier échoue, et ce qu'il avait enregistré avant reste actif (`b.backend` garde son
  hook). Le gagnant est simplement le premier par ordre alphabétique. Deux mods qui `provides` le
  même id virtuel : le dernier gagne en silence (`resolver.py:66-67`).
- **[lu]** : `bootstrap_all_mods` ignore `report.disabled_mods` et `report.warnings`
  (`loader.py:252-264`). `axiom mods list` n'affiche ni l'ordre, ni les conflits, ni les raisons de
  désactivation (`mods_cmd.py:276-295`).
- **Correction** : un exclusif garde **tous** les candidats et `get_slot` rend celui que l'ordre
  désigne, avec `axiom mods conflicts` / `list` qui montre « A et B fournissent X, A gagne ».
  Ajouter `mod_order` dans la config.

#### I7. Le format `.axmod` ne marche pas pour les mods à plusieurs fichiers
- **[lu]** : depuis une archive, seul `main.py` est exécuté (`loader.py:178-202`). Les mods
  officiels importent leurs autres fichiers via `mods.axiom.<id>.<fichier>`
  (ex. `mods/axiom.living_memory/main.py:17-20`), ce qui pointe vers le **dossier `mods/` du
  repo**, pas vers l'archive.
- **[exécuté]** : `axiom.living_memory` empaqueté puis chargé avec un `mods/` vide donne
  `ModLoadError: 'module' object is not callable`. Le chargement depuis le repo « marche »
  seulement parce que les sources sont aussi sur disque.
- **Bug associé [exécuté]** : le finder de `mods/__init__.py:76-80` renvoie un paquet vide pour
  **n'importe quel** nom `mods.*`. `import mods.does_not_exist.at_all` réussit. Les
  `try/except ImportError` des mods ne servent donc à rien, et une faute de frappe donne un module
  vide au lieu d'une erreur. C'est la cause du message « module object is not callable » ci-dessus.
- **Concrètement** : distribuer un vrai mod tiers en `.axmod` (le format promis en §5.1) ne marche
  pas dès qu'il a plus d'un fichier.
- **Correction** : charger l'archive avec `zipimport` ou l'extraire dans un cache, puis l'importer
  comme paquet (`axiom_mod_<id>`) pour que les imports relatifs marchent. Le finder doit renvoyer
  `None` quand rien ne correspond.

#### I8. La découverte des mods dépend du dossier courant
- **[lu]** : `discover_installed_mods` cherche dans `Path("mods")` et `Path("dist/mods")`, chemins
  **relatifs** (`mods_cmd.py:65`). Même chose pour l'installation du store (`store.py:208,280-281`),
  le scaffold (`scaffold.py`, `Path("mods")`) et le créateur LLM (`llm_creator.py:198,281`).
- **[exécuté]** : `bootstrap_all_mods` lancé depuis `/tmp/...` donne `services []`, `hooks {}`.
  Aucun mod n'est chargé.
- `pyproject.toml:59` ne publie que `axiom*`. Un `pip install axiomai-engine` n'a donc **aucun**
  mod, et le tour ne peut pas fonctionner.
- **Concrètement** : lancer Axiom depuis un autre dossier (raccourci, terminal ouvert ailleurs,
  install pip) donne un moteur sans tour de jeu.
- **Correction** : dossiers de mods absolus (`paths.get_mods_dir()` dans le dossier de données de
  l'utilisateur, plus le dossier des mods officiels relatif à l'installation).

#### I9. Créateur LLM : le code généré s'exécute AVANT la confirmation, et peut écrire hors du dossier de préparation
- **[exécuté]** avec un faux LLM : `generate_mod` appelle `test_mod(staged_dir)`
  (`llm_creator.py:265`), qui **exécute `main.py` et `init(ctx)` dans le processus**
  (`tester.py:172-195`), puis pytest sur les tests générés (`tester.py:205-232`). Résultat :
  `code executed before user confirmation: True`.
- **[exécuté]** : une clé de fichier `../../escaped.txt` dans la réponse du LLM est écrite **hors**
  du dossier de préparation (`llm_creator.py:248-251`). Avec le dossier par défaut
  `~/.cache/AxiomAI/staged_mods/<id>`, `../../../` atteint le dossier personnel.
- Les **patches** posés par un mod pendant ce test sont globaux : `ctx.cleanup()` retire tous les
  patches de ce `mod_id` (`context.py:88-89`), y compris ceux d'un mod du même id déjà chargé.
- **Violé** : §12. Le diff + confirmation devait protéger contre « un mod dicté par du contenu
  importé ». Ici le code tourne avant que l'utilisateur ait vu le diff.
- **« Staging sandbox » vs D14** : le mot « sandbox » est trompeur, ce n'est qu'un dossier
  temporaire. Ce dossier est **légitime** : c'est ce qui permet de montrer un diff avant d'écrire
  dans `mods/`. Il n'y a pas de sur-ingénierie de sécurité contraire à D14. Le problème est
  l'inverse : la seule protection prévue est contournée.
- **Autres [lu]** : le prompt système présente des hooks **que personne ne déclenche** (voir I10)
  et une règle `first_win` qui n'existe pas (`llm_creator.py:43`). `apply_generated_mod` copie par
  dessus le dossier existant sans supprimer les anciens fichiers (`llm_creator.py:303-309`).
  `/api/mods/apply` installe n'importe quel dossier dont le client donne le chemin
  (`main_web.py:2379-2386`) ; c'est acceptable sous D14 en local, à noter.
- **Correction** : avant confirmation, uniquement un **diff + validation statique** (manifeste,
  noms de hooks connus, AST). Les tests ne tournent **qu'après** le « oui ». Rejeter les chemins qui
  sortent du dossier de préparation.

#### I10. Le scaffold et le créateur LLM enseignent des hooks qui ne sont jamais déclenchés
- **[lu]** (grep des `invoke_hook/execute_hook`) : les hooks réellement déclenchés sont
  `axiom.kernel:execute_step`, `axiom.step:gather_context`, `axiom.step:arbitrate_mutations`,
  `axiom.step:after_step`, `axiom.turn:arbitrate_stats` et `axiom.universe:*`.
- Les modèles de `axiom mod new` utilisent `axiom.turn:after_step` et `axiom.turn:gather_context`
  (`scaffold.py:63-65,77-80,150,179-180`). Le prompt du créateur LLM annonce en plus
  `axiom.turn:execute_step`, `axiom.time:tick` et `axiom.world:rules` (`llm_creator.py:58-68`) :
  **aucun n'est déclenché**.
- **Concrètement** : un mod créé par `axiom mod new` ou par le LLM se charge, passe `axiom mod test`,
  puis **ne fait rien** en jeu, sans erreur. C'est exactement le contraire de §12 (« API petite,
  stable, documentée »).
- **Correction** : une liste unique des hooks et emplacements publics (constantes dans `axiom.turn`),
  utilisée par le scaffold, le prompt du créateur, `tester` (refuser un hook inconnu) et la doc.

#### I11. Mode sans échec : il garde tous les mods « officiels », et « officiel » se réduit à un préfixe
- **[lu]** `loader.py:52-60` : en safe mode, seuls les ids qui ne commencent pas par `axiom.` ou
  `core.` sont exclus.
- **[exécuté]** : un mod tiers nommé `axiom.evil` est chargé en mode sans échec (`services ['evil']`).
- **Violé** : §4.1 (« démarrer sans **aucun** mod »), D2 (les mods officiels ont un statut que les
  tiers n'ont pas). Aucun registre de noms ne réserve `axiom.*`.
- **Concrètement** : si c'est un mod officiel qui casse (ou un mod tiers qui se fait passer pour
  officiel), le mode sans échec ne sauve rien.
- **Correction** : safe mode = aucun mod, ou la liste minimale explicite de §4.4 (chat + chargement
  du modèle), choisie par l'utilisateur. Réserver `axiom.*` aux mods livrés avec l'installation.

#### I12. Store (phase 5) construit avant ses préalables, avec un catalogue introuvable
- **Préalable ignoré** : §13 Phase 5 dit « trancher la licence des mods, l'installeur pip » avant
  le store. La licence a été « tranchée » par l'agent dans `docs/licensing_mods.md` (tiers « au
  choix de l'auteur », patches = AGPL). Le §14 actuel ne contient **aucune nouvelle ligne de
  décision utilisateur**, seulement la phrase modifiée des « questions reportées » (`DOC.md:546`).
  C'est une question juridique (l'original demandait un « avis juridique », §14).
- **Catalogue [exécuté]** : `dist/mods/store_index.json` **n'existe pas** dans le repo (`dist/` est
  dans `.gitignore:9`). Sans `--repo`, `fetch_store_index` se rabat sur un catalogue **vide**
  (`store.py:96-102`). L'URL par défaut publiée est `https://mods.axiomai.org/downloads/...`
  (`store.py:335`), un domaine non vérifié **[supposé fictif]**. Le TODO, lui, affirme « Catalogue
  officiel initial (`dist/mods/store_index.json`) ». Les docs phase 5 donnent l'option `--index`,
  alors que la CLI attend `--repo` (`phase-5.../DOC.md:105,110` vs `mods_cmd.py:187`).
- **D-7** : respecté (pas d'installeur pip).
- **Défauts [lu]** : « dernière version » = première entrée du catalogue (`store.py:238-240`) ;
  l'install se fait dans `./mods`, c'est-à-dire **dans le code source** du repo, avec `rmtree` du
  dossier existant (`store.py:271-273`) ; l'id du catalogue n'est pas comparé à l'id du manifeste,
  donc une entrée `x.y` peut écraser `mods/axiom.turn` ; pas de commande `uninstall`, et une copie
  `.axmod` laissée dans `dist/mods/` est rechargée par `discover` après suppression du dossier
  (`mods_cmd.py:65,84-90`).
- **Concrètement** : le store est aujourd'hui un **client sans serveur** : du code qui marche en
  local, mais rien à installer. Le plus gros risque est d'avoir figé une licence sans décision
  tracée.
- **Correction** : geler le store (le garder derrière un drapeau ou le sortir du noyau, c'est un
  bon candidat de mod) jusqu'à la décision sur la licence, et la tracer dans §14.

### MINEUR

- **m1. Manifeste lu mais en partie ignoré** : `hash` et `[schema]` ne sont pas lus du tout ;
  `storage` est lu mais jamais utilisé (grep `manifest.storage` : 0) ; `contributes.hooks/slots`
  ne sont vérifiés que par regex dans `tester.py:140-150`, jamais comparés à ce que le mod
  enregistre vraiment ; `apply_mod_migrations` (`schema.py:1278`) existe mais n'est appelée ni par
  le noyau ni par `ModContext`. Aucun modpack n'est enregistré dans les saves (grep `modpack`
  dans `axiom/` : 0) alors que le TODO coche « modpack ». (§5.2, §10.3, D13.)
- **m2. Ordre des patches par priorité, pas par ordre de chargement** (`patcher.py:282`) : §8 dit
  que l'ordre utilisateur ordonne aussi les patches empilés. [exécuté, cas 10]
- **m3. Un patch qui lève une exception casse l'appelant** (`patcher.py:292-312`, [exécuté] cas 8).
  §6.1 ne l'exige pas pour les patches, mais c'est incohérent avec l'isolation des hooks.
- **m4. Le gel des patches est un booléen global non réentrant** : un `step_patch_freeze()`
  imbriqué déverrouille à sa sortie ([exécuté] cas 9 : `still locked after inner exit? False`), et
  le gel s'applique à tous les threads du serveur web.
- **m5. Fonctions récursives** : le patch par `__code__` est appliqué à chaque niveau de récursion
  ([exécuté] `fact(4)` → 4 appels du patch).
- **m6. Les mods officiels utilisent l'API privée** `ctx._registry` (15 occurrences dans `mods/`,
  ex. `mods/axiom.turn/main.py:175`), parce que `ModContext` n'expose ni `invoke_hook` ni
  `get_slot`. C'est un symptôme de D2 et le signe que l'API publique ne suffit pas.
- **m7. Windows** : `tester.py:211` construit `PYTHONPATH` avec `:`, ce qui casse sous Windows
  (il faut `os.pathsep`). Le lien symbolique `mods/axiom_ui_qt -> axiom.ui.qt` n'est importé par
  aucun code (grep). Sous Windows sans support des liens, il devient un petit fichier texte, sans
  effet. Sous Linux, `discover` voit le mod deux fois et charge celui du lien. Il est inutile, à
  supprimer. Encodages : toutes les lectures du noyau sont en UTF‑8 explicite.
- **m8. `tester` (D4)** : la liste des imports d'UI interdits oublie **PySide6**, la vraie
  bibliothèque Qt du projet (`tester.py:30-35`), et toute dépendance dont l'id contient « ui »
  passe (`tester.py:153-156`).
- **m9. Une dépendance Python manquante fait sauter le mod en silence** (seulement un log,
  `loader.py:91-95`). Le DOC disait « avertir ». Refuser de charger est défendable, mais il faut
  l'afficher dans `mods list`.
- **m10. `axiom mods patches`** affiche les patches *déclarés* seulement si aucun n'est actif.
  Dans un processus CLI neuf, aucun mod n'est chargé, donc on ne voit jamais les patches réels
  (`mods_cmd.py:211-233`).
- **m11. `ctx.config`** est le même dictionnaire que celui qui porte `enabled`
  (`context.py:35`, `mods_cmd.py:304`), et aucune méthode ne le sauvegarde.
- **m12. Garde anti-fuite contournée** : `export_engine.py:49` interdit `import mods` dans le
  moteur, mais `axiom/kernel/__init__.py:83-89` et `loader.py:28-31` le font via
  `importlib.import_module("mods")`, que la regex ne voit pas.
- **m13. `axiom/cli/test.py`** : simple brouillon qui lance `pytest tests/test_golden_step.py` avec
  un chemin relatif. Ce n'est pas le `axiom mod test` sur harnais golden step promis par §12 :
  `tester.py` ne s'appuie pas du tout sur le harnais.
- **m14. Un test pollue le repo** : `tests/test_mod_creator.py` a créé
  `dist/mods/community.fatigue-0.1.0.axmod` dans le repo pendant ma session (horodatage 00:10).
  Ce mod est ensuite apparu **comme installé et activé** dans `axiom mods list` [exécuté]. Je l'ai
  supprimé (fichier ignoré par git, créé par mon lancement de test).

---

## 4. Tests lancés

`.venv/bin/python -m pytest tests/<fichier>.py -q`, fichier par fichier :

| Fichier | Résultat |
|---|---|
| `test_kernel_loader.py` | 13 passed |
| `test_patching_system.py` | 6 passed |
| `test_mod_creator.py` | 14 passed (laisse un artefact, m14) |
| `test_mod_store_and_packaging.py` | 9 passed |
| `test_mods_decoupling_and_effectivity.py` | 7 passed |
| `test_mod_localization.py` | 9 passed |
| `test_ui_mods_and_cli.py` | **7 passed, 1 failed** : `test_manifests_and_loading_ui_mods` attend `dist/mods/axiom.ui.web.axmod`, un fichier ignoré par git qui n'existe que sur la machine de Frosoore |
| `test_world_turn_mods.py` | 6 passed |

Ces tests couvrent les cas nominaux. **Aucun** ne teste : un patch sur une méthode ou une closure,
la désactivation d'un mod fautif, `axiom_api` incompatible, une spec de version de dépendance,
un conflit qui ne bloque pas les autres mods, ni un `.axmod` multi-fichiers sans les sources sur
disque. Tous ces cas échouent (section 3).

Scripts de vérification : `/tmp/claude-1000/axiom-review/t_resolver.py`, `t_boot.py`,
`ws/t_ws.py`, `pt/t_patch.py`, plus les commandes en ligne pour l'archive et le créateur LLM.

---

## 5. Écarts entre ce que la doc ou le TODO affirment et ce que fait le code

| Affirmation (TODO.md / docs de phase) | Réalité |
|---|---|
| Phase 1 « mode sans échec » fait | Garde tous les `axiom.*`/`core.*`, accepte un tiers nommé `axiom.*` (I11) |
| Phase 1 « Stockage par politiques + modpack » fait | Pas de `ctx.store` ; `[storage]` du manifeste ignoré ; modpack non enregistré dans la save (m1) |
| Registre « exclusif / chaîne / collecte » | Exclusif = « le premier arrivé gagne, le second plante » ; `get_slot` d'une chaîne rend une liste (`registry.py:150-151`) ; pas d'ordre utilisateur (I6) |
| `ModContext` : « Enforces Rule D11 (automatic total unregistration) » (`context.py:4`) | Jamais appelé en production ; ni threads ni emplacements déclarés couverts (I3) |
| Phase 3 « Mécanisme de secours `__code__` » | Seulement pour les fonctions de module sans closure ; méthodes et closures échouent en silence (B2) |
| Phase 3 « Inspection CLI `axiom mods patches` » | Liste des patches inopérants comme actifs (B2, m10) |
| Phase 4 « `axiom mod test` » | N'utilise pas le harnais golden step (§12) ; exécute le code (m13, I9) |
| Phase 4 « staging sandbox, diffs, tests automatiques et garde-fous de confirmation » | Les tests exécutent le code **avant** la confirmation ; écriture hors du dossier de préparation possible (I9) |
| Phase 5 « Cadre juridique et licence des mods » | Décidé par l'agent, aucune décision utilisateur au §14 (I12) |
| Phase 5 « Catalogue officiel initial `dist/mods/store_index.json` » | Fichier absent du repo (gitignoré) (I12) |
| Phase 5 « Suite de tests 9/9 au vert » | Vrai, mais `test_ui_mods_and_cli` échoue hors de la machine de l'auteur |
| Phase 1 « pluggy écarté au profit d'un registre plus hermétique et **sécurisé** » | « Sécurisé » contredit l'esprit de D14 ; le registre n'a d'ailleurs aucun mécanisme de sécurité |
| Ordre §13 : préalables D-1 (TICKET-100→105) et coordination D-6 avant les phases | Toujours **non cochés** dans `TODO.md` alors que les phases 0 à 5 sont cochées (D17/D-2) |

---

## 6. Questions pour Frosoore / le propriétaire

1. **Licence des mods** : la règle de `docs/licensing_mods.md` (tiers « au choix », patches = AGPL)
   est-elle une décision du propriétaire ? Si oui, il faut l'inscrire au §14. Sinon, on retire le
   document en attendant un avis.
2. **Store** : le gèle-t-on (ou le sort-on du noyau vers un mod) tant que la licence n'est pas
   tranchée et qu'aucun serveur de catalogue n'existe ?
3. **Patches sur méthodes** : sans eux, la promesse de profondeur (D8) n'est pas tenue. Accepte-t-on
   de rouvrir la phase 3 avant tout merge ?
4. **Mode sans échec** : « aucun mod » strict (DOC d'origine), ou « mods livrés avec l'installation »
   (choix actuel) ? Dans le second cas, il faut une liste explicite et non un préfixe de nom.
5. **`axiom.kernel:execute_step` et `KernelStepContext`** : le propriétaire valide-t-il que le noyau
   porte `llm`/`vector_memory`/`hero_entity_id`, ou faut-il un step réellement générique (D-3) ?
6. **Créateur LLM dans le noyau** : D1 dit non. Le déplace-t-on dans un mod `axiom.mod_creator` ?
7. Pour Frosoore : les mods sont-ils censés tourner depuis `pip install axiomai-engine` ? Si oui,
   où vivent les mods officiels, et comment sont-ils trouvés indépendamment du dossier courant (I8) ?
8. Pour Frosoore : quels noms de hooks font foi, `axiom.step:*` ou `axiom.turn:*` ? Les modèles et
   le prompt du créateur utilisent les seconds, le moteur déclenche les premiers (I10).
