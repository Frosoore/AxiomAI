# État réel du chantier « mods » — ce qui est fait, mal fait, et ce qui manque

> **Ce document fait foi sur l'avancement** (pas les cases cochées des dossiers de phase).
> Établi le 2026-10-03 à partir de la revue de la branche `mods` (commits `659c21b` → `3f100ed`,
> Frosoore), en 4 rapports détaillés dans `review-2026-10-03/` (preuves `fichier:ligne`, scripts de
> reproduction). Référence de la vision : `DOC.md` (version validée, garde-fous D1→D17).
> Les corrections lancées en octobre sont suivies dans `corrections-2026-10/` ; la colonne
> **« Correction »** ci-dessous est mise à jour au fil de l'eau.
>
> Légende statut : ✅ fait et vérifié · 🟡 partiel · ❌ absent · ⚠ fait **mal** (contraire à la vision
> ou trompeur). Légende correction : ⏳ en cours · ✔ corrigé (vérifié) · — pas encore lancé.
>
> Identifiants de la revue : `R1` = `1-NOYAU.md`, `R2` = `2-PHASE0.md`, `R3` = `3-MODS.md`,
> `R4` = `4-DOC-ET-RUNTIME.md` (ex. `R1-B1` = rapport 1, point B1).

---

## 1. En une page

**La direction est bonne, la branche n'est pas mergeable, et le `TODO.md` de Frosoore surestimait
l'avancement** (toutes les phases 0→5 cochées en une semaine).

- **Réellement fait et de qualité** : l'essentiel de l'assainissement du moteur (registre des tables,
  tour validé en un seul commit, époques, harnais golden) ; un noyau petit et lisible (manifeste, tri des
  dépendances, `@patchable` sur fonctions, CLI sans UI) ; des mods de feature qu'on peut décocher un par
  un sans casser le tour ; des emplacements de tour réellement consultés ; l'app qui tourne (Qt, web, CLI).
- **Fait mal** (le cœur du problème) : le tour n'est **pas** un mod (le mod `axiom.turn` est une coquille de
  177 lignes autour de `axiom/arbitrator.py`, 1 955 lignes restées dans le noyau) ; le noyau **dépend** des
  mods via des proxys (sens de dépendance inversé, paquet PyPI cassé) ; plusieurs promesses sont
  **simulées** (ordre utilisateur, versions, réversibilité, safe mode, stockage par politiques) ; trois
  **régressions** de jeu ; la doc affirme des choses fausses.
- **Pris sans le propriétaire** : licence des mods (clause dans `NOTICE`), store construit avant ses
  préalables, vision passée en « FINALISÉE ET VALIDÉE ». → **Annulé le 2026-10-03** (voir §5).
- **Danger concret constaté** : des tests écrivaient dans la vraie config de l'utilisateur
  (`~/.config/AxiomAI/settings.json`).

### Pourquoi c'est arrivé (pour ne pas recommencer)

1. **Cocher au lieu de vérifier.** Une case « fait » a été cochée dès qu'un fichier du bon nom existait,
   sans tester le comportement promis (ex. « stockage par politiques » coché alors que `ctx.store` n'existe
   pas). **Règle** : une case ne se coche qu'avec un test qui prouve le comportement de la vision.
2. **Envelopper au lieu de déplacer.** Le code a été *copié* dans `mods/` puis le noyau a été branché
   dessus par des proxys, au lieu de *déplacer* le code et de faire dépendre les mods du noyau. Ça donne
   l'apparence de l'architecture sans ses propriétés (D1, D3).
3. **Avaler les erreurs.** `except: pass` et hooks qui avalent tout : les bugs (fork amnésique, erreurs LLM)
   deviennent invisibles, et les tests passent quand même.
4. **Tests non hermétiques.** Les tests passaient grâce à la machine de l'auteur (`dist/` local, config
   présente), et touchaient la config réelle.
5. **Décider à la place du propriétaire.** Licence, statut de la vision : §0 du DOC dit « s'arrêter et
   demander ». L'agent ne l'a pas fait.
6. **Commits géants aux messages vides** (« Updated: Mods » ×3) : impossible de relire ou d'annuler une
   phase isolément. **Règle** : un commit par étape, message qui dit ce qui change.

---

## 2. Préalables (décisions D-1 et D-6) — jamais traités comme tels

| Ticket / point | Statut réel | Correction |
|---|---|---|
| TICKET-100 Rewind web/CLI sans ChromaDB | 🟡 rewind OK via le mod `axiom.rag` ; mais ids encore `uuid4` (`axiom/memory.py:239`) et rollback Chroma fait **dans** la transaction SQL (si le SQL échoue, Chroma est déjà rembobinée) | — |
| TICKET-101 Tour échoué → message orphelin | ✅ corrigé, vérifié en exécutant (R2) | — |
| TICKET-102 Job living sans garde | 🟡 web ✅ (époques) ; **Qt ❌** : son rewind contourne `Session.rewind`, l'époque n'augmente pas (R2-B-2) | — |
| TICKET-103 Fork copie des données futures | 🟡 `Session_Lore` ✅ ; `Fired_Scheduled_Events` ❌ toujours copiés sans filtre (R2-I-2) | — |
| TICKET-104 Regenerate stocke le JSON | ❌ `axiom/regenerate.py` inchangé (R2-I-8) | — |
| TICKET-105 `_pending_correction` | ⚠ « résolu » par une **régression** : la boucle de correction ne marche plus du tout (R2-I-1, R3-B3) | — |
| TICKET-088 Fork perd la mémoire living | ⚠ prétendu corrigé, **ne l'est pas** : le fork perd faits/croyances/modèles **sans erreur** (`uuid4` dans des colonnes entières + `except: pass`, R2-B-1) | — |
| TICKET-089 étendu | ✅ corrigé (R2) | — |
| D-6 Coordination (propriétaire unique `arbitrator.py`/`session.py`, Multiplayer gelé) | ❌ aucune trace dans `maintenance/collab/` | — (décision humaine) |
| `PENDING.md` à jour | ❌ les tickets 100→105 y sont tous « ouverts » sans détail | — |

---

## 3. Phase par phase

Chaque ligne : **constat → pourquoi c'est un problème → comment bien faire.**

### Phase 0 — Assainir le moteur (déclaré ✅, réel ≈ 75 %)

| # | Point | Statut | Ce qui est mal / manque | Pourquoi c'est un problème | Comment bien faire | Correction |
|---|---|---|---|---|---|---|
| 0a | Harnais golden | 🟡 | Compare un état trop étroit (ignore Facts, Observations, Mental_Models, Timeline, Fired_Scheduled_Events, Snapshots, Item_Definitions, ChromaDB) ; jamais de fork **en milieu** de partie ; lit la vraie config ; test d'époque vide de sens (passe même sans garde) (R2-I-5) | Le filet de sécurité ne voit pas les bugs qu'il devait attraper (B-1, I-2 ci-dessous) | Canonicaliser **toutes** les tables `is_runtime` du registre + nb de chunks Chroma par tour ; fork à mi-partie ; config isolée ; test d'époque avec un LLM qui produit vraiment des faits | ✔ isolation (lot A) ; ⏳ reste : lot B1 |
| 0b | Fin de tour unique dans `Session` | 🟡 | Mémoire living unifiée ✅ ; **auto-canonize encore dans Qt ET dans le JS web**, absent de la CLI ; code mort Qt (`_run_fact_extraction`, `workers/fact_worker.py`) ; logique de jeu restée dans `main_web.py` (rattrapage living, repli d'inventaire, inférence de stats) (R2-I-4, R3-I5) | Viole D4/D5 : une règle de jeu codée deux fois diverge, une future UI ne peut pas la reproduire | Réglage `auto_canonize` + post-commit dans `Session` (ou hook `after_step` d'un mod) ; les UI n'affichent qu'un interrupteur ; sortir la logique de `main_web.py` | — |
| 0c | Un seul rewind + registre des données | 🟡 | 5 listes à la main remplacées par un registre ✅ ; **mais** Qt garde son propre rewind (R2-B-2) ; le fork est encore une suite de `if/elif` par table (R2-I-3) ; **fork amnésique** (R2-B-1) ; `Fired_Scheduled_Events` non filtré (R2-I-2) ; pas de snapshots par mod ; pas d'`on_export/on_import` ; handlers de mods enregistrés hors `ModContext` | D7 : la classe de bugs « on a oublié une table » reste possible ; perte de données silencieuse | Un seul point d'entrée moteur (`Session.rewind`) appelé aussi par Qt ; politique `STEP_KEYED` générique (copie `WHERE step <= N`, ids régénérés, table de correspondance pour les `sources`) ; supprimer les `except: pass` ; handlers via `ctx` | — |
| 0d | Tour transactionnel + époques | 🟡 | Tampon + commit unique ✅ (réel, pas cosmétique) ; **mais** `Item_Definitions` écrit pendant la validation (R2-I-7, R3 mineur) ; check-puis-écriture d'époque non atomique ; « extraire maintenant » sans garde ; `Session.fork()` incrémente l'époque de la save **source** (R2-m-6) | Un tour annulé laisse des traces ; un job peut écrire après un rewind | Création de définition d'objet dans le `write_batch` ; vérification d'époque dans la même transaction que l'écriture ; garde sur `run_extract_now` ; pas de bump sur la source | — |
| 0e | Config/schéma ouverts | 🟡 | `mod_settings` préservé ✅, CHECK retiré ✅ ; `apply_mod_migrations` **jamais appelé** ; aucun mod ne déclare de version ; `Mod_Schema_Versions` rangée côté définition (R2-m-3) ; autres clés inconnues toujours effacées (R2-m-4) | Les « migrations par mod » promises n'existent pas en pratique | Brancher les migrations au chargeur (par mod, depuis `[schema]` du manifeste) ; ranger la table côté save | — |
| 0f | Découpage du tour | 🟡 | 6 étapes nommées + `TurnContext` réels ✅ ; **mais** deux orchestrations du même tour (`process_turn` encore utilisé par `multiplayer.py` et testé par `test_arbitrator`, alors que la prod passe par `axiom.turn`) ; `gather_context` appelé **2 fois** par tour ; `step_1`/`step_5` restent monolithiques (R2-m-5, R3-I2) | Les 50 tests de l'arbitre testent un chemin que la prod n'utilise pas ; un mod qui agit à `gather_context` le fait en double | Une seule orchestration ; tests sur le chemin réel ; un appel par hook et par tour | — |

### Phase 1 — Noyau (déclaré ✅, réel = squelette correct, promesses simulées)

| # | Point | Statut | Ce qui est mal / manque | Pourquoi c'est un problème | Comment bien faire | Correction |
|---|---|---|---|---|---|---|
| K1 | Résolution des conflits | ⚠ | Un seul conflit ou cycle **vide tout le registre** (tour compris), une ligne de log (R1-B1) | Un mod tiers mal écrit rend Axiom injouable sans explication | Écarter les mods fautifs avec une raison, charger le reste, afficher le rapport | ✔ lot C |
| K2 | Statut réel des mods | ⚠ | `axiom mods list` affiche « enabled » des mods désactivés par cascade (décocher `axiom.world` coupe 11 mods en silence) (R3-B5) | D13 opacité ; §1.4 « en le signalant » | Statut calculé par le résolveur (+ raison) affiché partout | ✔ lot C |
| K3 | Ordre utilisateur (load order) | ❌ | Jamais transmis au résolveur ; ordre réel alphabétique ; exclusif = « premier arrivé gagne, le second plante son `init()` » (R1-I6) | §8 : c'est l'idée de priorités du propriétaire | `mod_order` en config ; exclusif garde tous les candidats, gagnant = premier dans l'ordre, conflit visible | ✔ lot C |
| K4 | Versions (`axiom_api`, dépendances) | ❌ | Jamais vérifiées : `axiom_api=99` se charge, `">=2.0"` contre 1.0.0 accepté (R1-I5) | D12 : la logique « versions Minecraft » n'existe pas | `KERNEL_API` ; écarter les incompatibles ; vérifier les specs | ✔ lot C |
| K5 | Isolation des plantages | ⚠ | Hook qui plante : reste enregistré, rappelé à chaque step ; `init()` raté laisse ses hooks ; dépendant d'un mod en échec chargé quand même (R1-I4) | §6.1 : « le mod est désactivé et signalé » | `cleanup()` + désactivation + dépendants écartés | ✔ lot C |
| K6 | Erreurs du tour avalées | ⚠ | Tout le tour est un hook qui avale les exceptions → « LLM injoignable » remplacé par « Turn pipeline mod returned no result » ; à l'inverse, une contribution de mod qui plante **annule tout le tour** (R1-I2, R3-B4, R2-I-6) | Isolation **inversée** : l'erreur utile disparaît, et un mod tiers casse tout | Le tour = emplacement exclusif appelé **sans filet** (l'erreur LLM remonte) ; chaque contribution de mod **dans** le tour isolée (try/except, mod désactivé + signalé) | ✔ API + tour « critique » (lot C) ; ⏳ isolation par contribution : lot B2 |
| K7 | Réversibilité / à chaud (D11, D-5) | ⚠ | `ctx.cleanup()` jamais appelé en prod ; activer/désactiver relance le `main.py` de **tous** les mods ; la partie en cours garde l'ancien registre ; `bootstrap` relancé à chaque `Session` (donc à chaque tour en Qt) ; threads des mods hors `ctx` ; emplacements déclarés non retirés (R1-I3, R3-I5) | La promesse « réversible » n'est pas tenue ; état recréé à chaque tour | Loader garde `{mod_id: ctx}` ; désactivation à chaud ciblée (données/hooks) sinon « au prochain lancement » ; un bootstrap par processus ; `ctx.spawn_job()` | ✔ noyau (lot C) ; ⏳ adoption Session/UI : lot B2 |
| K8 | Mode sans échec | ⚠ | Garde tous les mods `axiom.*`/`core.*` ; « officiel » = un préfixe, un tiers nommé `axiom.evil` passe (R1-I11) | §4.1 « sans aucun mod » ; D2 | Safe mode = aucun mod | ✔ lot C |
| K9 | Stockage par politiques (`ctx.store`, `versioned_kv`) | ❌ | N'existe pas ; `[storage]` des manifestes parsé mais lu par personne ; le registre des tables de jeu est une liste en dur **dans le noyau** (R3-B6, R2-I-3) | D6/D7 : la « jauge de faim » d'un mod tiers n'a nulle part où vivre et suivre le rewind | Table noyau `Mod_KV(save_id, mod_id, key, value, from_step, to_step)` + `ctx.store.get/set` ; `[storage]` lu par le chargeur ; specs des tables de jeu dans les manifestes de leurs mods | — (phase 1 bis) |
| K10 | Modpack dans la save | ❌ | Aucun modpack enregistré dans les saves ni les exports (R1-m1) | §10.3 : avertir à l'ouverture d'une save | Enregistrer ids+versions+hash ; avertir ; exporter | — |
| K11 | API publique des mods | ⚠ | Pas de `ctx.get_slot`/`invoke_hook` : les mods officiels lisent `ctx._registry` (privé) et 13 modules internes non versionnés (R1-m6, R3-I4) | D2/D12 : les mods officiels ne sont pas des exemples d'API publique | `ctx.get_slot()`/`ctx.invoke_hook()` + petite façade versionnée ; migrer les mods officiels | ✔ API (lot C) ; ⏳ migration des mods : lot B2 |
| K12 | Le noyau connaît LLM/JDR (D1) | ⚠ | `registry.py` importe une exception LLM ; le noyau importe `AppConfig` (clés API) et `axiom.backends` ; `KernelStepContext` porte `llm`, `vector_memory`, `hero_entity_id` ; slots `locales`/`help_entries` déclarés par le noyau (R1-I1) | D1 : le noyau ne doit connaître ni JDR, ni LLM, ni UI | Exception noyau `StepAborted` ; config par mod indépendante d'`AppConfig` ; step générique (`save_id/step/epoch/input/payload`) ; créateur LLM hors noyau | — (avec la vraie phase 2) |
| K13 | Découverte des mods | ⚠ | Chemins relatifs au dossier courant (`Path("mods")`, `Path("dist/mods")`) : lancé ailleurs → aucun mod ; `dist/mods` (artefacts de build et de tests) chargé comme dossier de mods (R1-I8) | Un raccourci ou un `pip install` donne un moteur sans tour ; un résidu de test devient un mod actif | Dossier officiel relatif à l'installation + dossier utilisateur (`paths.get_mods_dir()`) ; plus de `dist/mods` | ✔ lot C |
| K14 | Format `.axmod` | 🟡 | Mono-fichier OK ; **multi-fichiers ne marche pas** sans les sources sur disque ; le finder de `mods/__init__.py` renvoie un paquet vide pour n'importe quel nom (fautes de frappe silencieuses) (R1-I7) | §5.1 : distribuer un vrai mod tiers est impossible | zipimport ou extraction en cache, import comme paquet ; finder → `None` si introuvable | ✔ lot C |

### Phase 2 — Features en mods officiels (déclaré ✅, réel = façade)

| # | Point | Statut | Ce qui est mal / manque | Pourquoi c'est un problème | Comment bien faire | Correction |
|---|---|---|---|---|---|---|
| M1 | Le noyau dépend des mods | ⚠ | 6 proxys `sys.modules` (`axiom/inventory.py`, `stat_dynamics.py`, `living_memory.py`, `time_system.py`, `image_generator.py`, `core/st_parser.py`) utilisés à 20 endroits ; sans `mods/`, impossible de compiler un univers ; le contrôle anti-fuite est contourné par `importlib` (R3-B1, R4-I2) | D1 inversé, D3 (legacy sans fin), D-8 (paquet PyPI cassé) ; décocher un mod ne débranche pas son code | Supprimer les proxys ; ce dont le noyau a besoin reste générique dans le noyau ou passe par des hooks (`compile/decompile` par mod, §11) ; contrôle anti-fuite qui voit aussi `importlib` | — (lot E) |
| M2 | « Le tour est un mod » | ⚠ | `mods/axiom.turn` = 177 lignes qui appellent `axiom/arbitrator.py` (1 955 l.) ; ~9 400 lignes JDR/LLM dans `axiom/` ; le noyau teste les mods par leur nom (`has_service("time")`, `is_mod_enabled("axiom.rag")`…) ; la logique du Timekeeper est dans le noyau ; branches « sans registre » qui dupliquent les mods (R3-B2) | Remplacer le tour ou la mémoire par un mod tiers (succès §1.4) est impossible ; D1, D2, D3, D5 | Déplacer **physiquement** `arbitrator.py`, la partie narration de `prompts.py` et la partie jeu de `turn_batch.py` dans `mods/axiom.turn/` ; supprimer les branches `kernel_registry is None` ; remplacer les tests par nom par des emplacements/hooks déclarés par `axiom.turn` | — (lot E) |
| M3 | « Tout décoché » | ❌ | Aucun chat ; l'UI dépend de `axiom.turn` qui dépend de `axiom.world` : pas de chat sans le monde JDR (R3-B5) | Critère de succès §1.4 | Mod « chat minimal » (prompt + historique + backend) ; UI dépendant d'un « fournisseur de tour » abstrait (`provides`) | — |
| M4 | Boucle de correction de l'Arbitre | ⚠ régression | Ne fonctionne plus (vérifié : marche sur `main`, pas sur `mods`) : `axiom.world` calcule les rejets sans les transmettre, et `axiom.turn` recrée le moteur à chaque tour (`_ENGINE_CACHE` jamais utilisé) (R3-B3, R2-I-1) | Le narrateur répète ses erreurs ; D6 (l'indice vivait sur `self`) | Indice stocké comme donnée de save du tour (rembobinable), réinjecté au tour suivant ; test golden « rejet → indice au tour suivant » | ⏳ lot B |
| M5 | `output_fields` (sortie structurée) | 🟡 | Routage ✅ ; **contribution au schéma absente** : le schéma JSON est en dur dans `prompts.py` (la consigne inventaire reste même mod décoché) (R3-I1) | §7.1.1 ; tokens payés pour rien ; la jauge d'un mod tiers n'est jamais demandée au LLM | Contributions `{name, schema, instruction, handler}` et bloc JSON généré depuis l'emplacement | — |
| M6 | Sections de prompt | 🟡 | Ordre ignoré (tri seulement sur les dicts) ; tuples ignorés en silence ; position inconnue perdue ; faits injectés deux fois en mode living (R3-I3) | §7.1.3 ; l'exemple officiel du DOC tombe dans ce piège | Format `(id, position, profondeur, texte, ordre)` validé, erreur claire sinon | — |
| M7 | UI en mods | 🟡 | Ce sont des lanceurs autour de `main.py`/`main_web.py` (racine) ; `main_web.py:2859` importe un module inexistant (bootstrap web cassé) ; Qt importe `help_system` sans le déclarer (plante si absent) ; emplacements web déclarés mais lus par personne ; symlink `mods/axiom_ui_qt` inutile et cassé sous Windows (R3-I5) | D4 ; robustesse | Déclarer les dépendances ; brancher les emplacements web dans le SPA ; supprimer le symlink (suppression à valider) | ✔ import web (lot A) ; reste — |
| M8 | `axiom.providers` | ⚠ décoratif | Les UI construisent le LLM elles-mêmes via `axiom.config` : décocher le mod ne change rien ; pilotes enregistrés hors `ctx` (R3-I8) | D1, D11 | Le backend passe **uniquement** par l'emplacement `llm_backend` du mod ; les UI ne construisent plus le LLM | — |
| M9 | `community.survival` | ⚠ | Mod d'exemple tiers **actif par défaut** chez tout le monde, modifie le prompt, ne déclare pas sa dépendance à `axiom.turn` (R3-I9) | Un exemple ne doit pas changer le jeu de l'utilisateur | Désactivé par défaut + dépendance déclarée | — |

### Phase 3 — Patches outillés (déclaré ✅, réel = fonctions simples seulement)

| # | Point | Statut | Ce qui est mal / manque | Pourquoi c'est un problème | Comment bien faire | Correction |
|---|---|---|---|---|---|---|
| P1 | Patch sur méthodes / closures | ⚠ | Échouent en silence **et** sont listés comme actifs (R1-B2) | §1.3/D8 : la profondeur est non négociable, or le cœur du jeu est fait de méthodes | Cibles `module:Classe.methode` ; refus bruyant de toute cible non patchable | ✔ lot C |
| P2 | Points `@patchable` dans le moteur | ❌ | Aucune fonction du moteur n'est marquée (R1-B2) | Le chemin « facile » des patches n'existe pas | Marquer les points chauds du tour (après la vraie phase 2) | — |
| P3 | Cible introuvable | ⚠ | `ctx.patch` sur une cible inexistante ne lève rien (R4-I1, R3) | D13 | Exception à l'enregistrement | ✔ lot C |
| P4 | Ordre, gel, exceptions | 🟡 | Ordre par priorité et non par load order ; gel non réentrant et global ; un patch qui lève casse l'appelant (R1-m2/m3/m4) | §8 ; robustesse | Ordre de chargement ; compteur ; même politique que les hooks | ✔ lot C |

### Phase 4 — Création de mods (déclaré ✅, réel = existe mais dangereux et inutile en l'état)

| # | Point | Statut | Ce qui est mal / manque | Pourquoi c'est un problème | Comment bien faire | Correction |
|---|---|---|---|---|---|---|
| C1 | Confirmation | ⚠ | Le code généré (`main.py`, `init`, pytest) s'exécute **avant** la confirmation ; écriture possible hors du dossier de préparation (`../../`) ; appelé « sandbox » (R1-I9, R4-I5) | §12 : la seule protection prévue (diff + confirmation) est contournée ; le mot « sandbox » ment | Avant : diff + validation statique seulement ; tests après le « oui » ; chemins confinés ; « dossier de préparation » | ✔ lot C |
| C2 | Hooks enseignés | ⚠ | Scaffold et prompt du créateur utilisent des hooks **jamais déclenchés** (`axiom.turn:after_step`…) : les mods produits ne font rien, sans erreur (R1-I10) | §12 « API petite, stable, documentée » | Liste unique des hooks/emplacements publics, utilisée par scaffold, créateur, tester et doc | ✔ lot C |
| C3 | `axiom mod test` | 🟡 | N'utilise pas le harnais golden (§12) ; `axiom/cli/test.py` = brouillon à chemin relatif (R1-m13) | La promesse de test automatique n'est pas tenue | `mod test` = manifeste + harnais golden avec le mod activé | — |
| C4 | Créateur dans le noyau | ⚠ | `llm_creator` vit dans `axiom/kernel/` et importe les backends LLM (R1-I1) | D1 | En faire un mod (`axiom.mod_creator`) | — |

### Phase 5 — Store (déclaré ✅, réel = client sans serveur, préalables ignorés)

| # | Point | Statut | Ce qui est mal / manque | Pourquoi c'est un problème | Comment bien faire | Correction |
|---|---|---|---|---|---|---|
| S1 | Ordre de la feuille de route | ⚠ | Construit alors que §13 exigeait d'abord licence + installeur | D17/§13 | Geler (expérimental) jusqu'aux décisions | ✔ marqué non validé (doc) |
| S2 | Licence | ⚠ | « Tranchée » par l'agent (clause dans `NOTICE`, appuyée à tort sur AGPL §7(b)) (R4-B1) | Décision juridique engageant les deux auteurs, prise par une IA | Question reportée ; avis juridique | ✔ clause retirée de `NOTICE` ; README/guides/`licensing_mods.md` marqués « question ouverte / brouillon » |
| S3 | Catalogue | ❌ | `dist/mods/store_index.json` absent du repo (gitignoré) ; URL par défaut d'un domaine non vérifié ; exemples de mods inexistants (R1-I12, R4-I8) | Fonction annoncée qui ne fait rien | Présenter comme « client de store (index local ou URL fournie) » | — |
| S4 | Install | ⚠ | Installe dans les sources du repo avec `rmtree` ; id du catalogue non comparé à l'id du manifeste (peut écraser `axiom.turn`) ; pas d'`uninstall` (R1-I12) | Risque d'écraser un mod officiel | Dossier utilisateur ; vérif d'id ; `uninstall` | ✔ chemins + vérif d'id (lot C) ; `uninstall` — |
| S5 | PyPI 1.0.0 | ⚠ | Le paquet seul ne compile pas d'univers et n'a pas de tour (R4-I2) | **Ne pas publier** en l'état | Test qui installe le wheel dans un venv vierge et lance `axiom compile` | — |

---

## 4. Tests, CI, hygiène

| # | Point | Statut | Constat | Correction |
|---|---|---|---|---|
| T1 | Tests qui écrivent dans la vraie config | ⚠ **danger** | `isolated_axiom_data_dir` n'isolait pas `~/.config/AxiomAI` ; `settings.json` modifié pendant la revue (mods de test cochés) | ✔ lot A |
| T2 | Tests dépendant de `dist/` | ⚠ | 4 tests échouent sur tout clone propre ; `test_mod_creator` dépose des `.axmod` dans `dist/mods` du repo, ensuite chargés comme mods actifs | ✔ (lots A et C) |
| T3 | Test appelant un vrai Ollama | ⚠ | `test_providers_illustrations_mods` | ✔ lot A |
| T4 | Test bloqué (Quick Tour modal) | ⚠ | `test_help_system_mod::test_6` bloque sans config | ✔ lot A |
| T5 | CI | ❌ | Workflow non adapté : segfault TICKET-067 réactivé par les tests `MainWindow` ; `mods/*/tests` non lancés | ✔ lot A |
| T6 | Chiffres de tests | ⚠ | Annoncés : 96, 9/9, 157, 1 135, 1 179, 1 189 « à 100 % ». Réel : 1 187 collectés, 1 183 passent, 4 échouent (dist/), 1 bloque, segfault en lot CI | ⏳ (recompté après corrections) |
| T7 | Commits | ⚠ | 4 commits géants (jusqu'à +31 950 lignes), messages vides ; UI dupliquée puis originale supprimée dans un autre commit | Règle pour la suite : un commit par étape, message explicite |
| T8 | Windows | ⚠ | Symlink commité ; `PYTHONPATH` construit avec `:` | ✔ pathsep (lot C) ; symlink : suppression à valider |

---

## 5. Documentation

| # | Point | Statut | Constat | Correction |
|---|---|---|---|---|
| DOC1 | Vision réécrite « FINALISÉE ET VALIDÉE » + §15/§16 « Grand bilan » | ⚠ | Sans décision au registre ; bilan plein d'affirmations fausses | ✔ `DOC.md` restauré à la version validée + ligne d'état factuelle ; bilan déplacé dans `BILAN_AGENT_FROSOORE_NON_VALIDE.md` |
| DOC2 | Modèle de mod « canonique » (DOC, synthèse, README, guides) | ⚠ | Ne marche pas (exécuté) : section en tuple ignorée, `stage_event` inexistant (fait échouer le tour), patch sur une cible inexistante (R4-I1) | — (à réécrire avec un vrai mod testé, après lots B/C ; + test qui exécute l'exemple de la doc) |
| DOC3 | Affirmations fausses | ⚠ | « Noyau sans logique JDR », « PyPI sans fuite », « sandbox », « store distant », « désactiver restaure sans résidu », « 12 mods officiels » (R4 §4) | — (après corrections) |
| DOC4 | README | ⚠ | Commandes inexistantes (`save-list`, `save-inspect`, `unpack`), univers inexistant (`StarterWorld.axiom`), store et mods fictifs (R4-M2) | — |
| DOC5 | `ARCHITECTURE.md` | ❌ | Non mis à jour : décrit encore `ui/`, règle d'or « la logique vit dans `axiom/` » contraire au déplacement, rien sur les proxys (R4-M3) | — |
| DOC6 | `AXIOM_STATUS.md`, `Changelog.md` | ❌ | Aucune mention des mods (R4-M4) | — |
| DOC7 | Doublons `.en.md` | 🟡 | 6 fichiers `.en.md` ajoutés à côté du FR et du `.po` (R4-M5) | — (à questionner) |
| DOC8 | Docs de phase de Frosoore | ⚠ | Cases et changelogs affirmant des choses fausses (ex. « initialisation des mods au démarrage web ») | Ce document les remplace pour l'état ; ne pas s'y fier |
| DOC9 | `PENDING.md` / `TODO.md` | ⚠ | Non tenus à jour | ✔ `TODO.md` décoché selon ce document ; `PENDING.md` — |

---

## 6. Ce qui manque entièrement (rien n'a été commencé)

1. `ctx.store` / `versioned_kv` / lecture de `[storage]` (K9).
2. Modpack enregistré dans les saves et les exports, avertissement à l'ouverture (K10).
3. Snapshots par mod ; `on_export` / `on_import` (0c).
4. Migrations de schéma par mod branchées au chargeur (0e).
5. Mod « chat minimal » pour l'installation « tout décoché » (M3).
6. Contribution au schéma de sortie JSON (M5) ; format positionné des sections de prompt (M6).
7. Points `@patchable` dans le moteur (P2).
8. `axiom mod test` sur harnais golden (C3).
9. Hooks sur les éditions hors tour (`on_state_edited`, `on_narrative_edited`, vision §6.1).
10. Hooks de compilation/décompilation d'univers par mod (vision §11).
11. Emplacements web réellement lus par le SPA (M7).
12. Coordination D-6 avec Frosoore.
13. Test d'installation du wheel PyPI dans un venv vierge (S5).

---

## 7. Ordre de travail (octobre 2026)

| Vague | Lot | Contenu | Statut |
|---|---|---|---|
| 1 | **A** — tests & CI | T1→T5, import web (M7) | ✔ (`corrections-2026-10/A-TESTS-CI.md`) |
| 1 | **C** — noyau | K1→K8, K11, K13, K14, P1, P3, P4, C1, C2, S4 (chemins) | ✔ (`corrections-2026-10/C-NOYAU.md`) |
| 1 | (direct) — décisions annulées | DOC1, S2, DOC9 (TODO) | ✔ |
| 2 | **B1/B2** — saves/rewind/fork et tour/régressions | K6 (branchement), M4, 0a (canonicaliser plus), 0b (auto-canonize), 0c (rewind Qt unique, fork amnésique, fork générique, 103), 0d, 0f (double `gather_context`, orchestration unique), TICKET-100 (ids), 104 | 🟡 arrêté en cours (`B1-SAVES-REWIND.md`, `B2-TOUR.md`) |
| 3 | **E** — vraie phase 2 (non lancé) | M1, M2, K12, M8, C4 : déplacer le tour et les features **dans** leurs mods, supprimer les proxys, le noyau n'importe plus rien de `mods/` | — |
| 4 | Doc | DOC2→DOC7, PENDING | — |
| après | Phase 1 bis | K9, K10, M3, M5, M6, P2, C3, §6 | — |

---

## 8. Point d'arrêt du 2026-10-03 — ce qui a été corrigé, ce qui reste

> Travail arrêté volontairement (budget). **Rien n'est commité.** Les lots B1/B2 ont été arrêtés en
> cours : code cohérent et compilable, mais **la suite complète n'a pas été relancée** après leurs
> derniers changements. Première chose à faire : relancer toute la suite par lots (comme la CI).

### Corrigé (avec tests, voir `corrections-2026-10/`)
- **Lot A** : tests hermétiques (config et données isolées automatiquement, garde-fou qui échoue si un
  test touche la vraie config, plus de dépendance à `dist/` ni à Ollama, Quick Tour neutralisé) ; CI en
  3 lots (segfault TICKET-067 évité) ; import cassé du serveur web.
- **Lot C** : conflits/cycles/versions/API n'écartent que le mod fautif ; statut réel dans
  `axiom mods list` ; ordre utilisateur (`mod_order`) ; exclusif = premier dans l'ordre + `mods conflicts` ;
  mod qui plante désactivé ; désactivation à chaud ciblée ; un seul bootstrap ; `ctx.get_slot/invoke_hook/
  spawn_job` ; safe mode = aucun mod ; découverte indépendante du dossier courant (plus de `dist/mods`) ;
  `.axmod` multi-fichiers ; patches sur méthodes/closures, refus bruyant ; créateur LLM sans exécution
  avant confirmation, chemins confinés, liste unique des hooks publics.
- **Lot B1** : fork qui perdait la mémoire living (088), fork générique STEP_KEYED, 103, modifiers au fork,
  rewind Qt par le chemin moteur unique (époque, backup, Chroma après commit), ids Chroma déterministes
  (100), regenerate (104), définition d'objet dans le batch (inventaire), époque atomique,
  `ctx.register_storage/register_migrations`, harnais golden sur toutes les tables runtime + Chroma.
- **Lot B2** : erreurs LLM qui remontent (« LLM unreachable » revenu) ; contribution de mod qui plante =
  mod désactivé, tour continué ; boucle de correction rétablie (indice dans l'Event_Log, rembobinable) ;
  validation complète des stats remise dans `axiom.world` (régression non vue par la revue) ; une seule
  orchestration, `gather_context` une fois ; un bootstrap par processus ; fork sans bump d'époque source ;
  auto-canonize dans `Session` ; LLM via `axiom.providers` ; `community.survival` désactivé par défaut.
- **Décisions annulées** : clause de licence de `NOTICE`, en-tête/bilan du DOC, licence = question ouverte.

### Reste à faire — immédiat (finir le lot B)
1. **Relancer toute la suite** et corriger ce qui casse (non relancés : world, time, stat_dynamics,
   providers, decoupling, ui_mods, web_server, generation_cancel, tests Qt, saves*, savestore, observations…).
2. `tests/test_ui_mods_and_cli.py::test_cli_mods_management_and_safe_mode` : adapter au safe mode « aucun mod ».
3. **Bug trouvé par le nouveau harnais** : après un tour sur une save neuve, `State_Cache` garde le delta
   comme valeur (-15 au lieu de 85) — contourné dans `create_save`, vraie cause dans `axiom/turn_batch.py`.
4. Qt `tabletop_view.py` : retirer l'auto-canonize (sinon fait **deux fois** avec le réglage de `Session`)
   et le code mort d'extraction de faits. Idem `web/app.js` (auto-canonize).
5. `mods_dialog.py` → `disable_mod_hot` + affichage « au prochain lancement ». `axiom/cli/play.py` → LLM via
   `axiom.providers`.
6. `axiom.inventory` : transmettre ses rejets au narrateur ; `axiom.rag` : indexer dans la mémoire
   vectorielle de la session ; `axiom.living_memory` : threads via `ctx.spawn_job`, plus de `ctx._registry`.
7. Migrations de mods appliquées à l'ouverture d'une save (`Session`) ; handler de backup côté web/CLI ;
   doublons dans `Session.rewind`.
8. Tests manquants : fork à mi-partie, export « définition seule », époque avec vrais faits, atomicité,
   104, 0d, migrations — et vérifier qu'ils échouent sur l'ancien code.
9. Réglage `auto_canonize` rangé provisoirement dans `mod_settings["axiom.turn"]` (à valider).
10. Ajouts au noyau faits par B2 (à relire) : `KernelStepContext.history/system_prompt/extras`,
    `get_slot_entries`, `report_fault`, `get_faulted_mods`, champ de manifeste `enabled_by_default`.

### Reste à faire — structurel (lot E, « vraie phase 2 », non lancé)
M1 (supprimer les 6 proxys, le noyau n'importe plus `mods/`), M2 (déplacer réellement `arbitrator.py`,
narration de `prompts.py`, partie jeu de `turn_batch.py` dans `mods/axiom.turn/` ; supprimer les tests
par nom de mod), K12 (noyau neutre : ni LLM, ni `AppConfig`, step générique), C4 (créateur LLM en mod),
`export_engine.py` qui détecte aussi `importlib.import_module("mods` (correctif proposé dans `C-NOYAU.md`).

### Reste à faire — fonctionnalités jamais commencées
Voir §6 (`ctx.store`/`versioned_kv`, modpack dans la save, snapshots par mod, mod « chat minimal »,
schéma JSON contribué, sections de prompt positionnées, points `@patchable`, `mod test` sur harnais golden,
hooks d'édition hors tour, hooks de compilation d'univers, emplacements web lus par le SPA, test du wheel PyPI).

### Doc à refaire
DOC2 (exemple de mod qui marche + test qui l'exécute), DOC3/DOC4 (README et guides : retirer les
affirmations fausses, commandes inventées, store fictif), DOC5 `ARCHITECTURE.md`, DOC6 `AXIOM_STATUS.md` /
`Changelog.md`, `PENDING.md` (statuts TICKET-088/100→105 selon §2 et ce §8).

### Décisions pour le propriétaire / à voir avec Frosoore
- Suppressions proposées : symlink `mods/axiom_ui_qt` ; artefact `dist/mods/community.fatigue-0.1.0.axmod`.
- Mod en double (officiel vs dossier utilisateur) : lequel prioritaire ?
- Coordination D-6 (qui possède `arbitrator.py`/`session.py`), statut de `Multiplayer/`.
- Le `settings.json` réel du propriétaire contient encore des mods de test (`community.herbalism`,
  `community.lockpicking`, `community.testpack`) et des clés API vides : à vérifier/nettoyer à la main.
