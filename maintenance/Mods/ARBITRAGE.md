# ARBITRAGE — Critique du système de mods

> Arbitrage indépendant du 2026-09-23. J'ai lu `DOC.md` en entier et `CRITIQUE.md` en entier, puis j'ai
> revérifié chaque référence `fichier:ligne` dans le code (commit `392644f` et arbre de travail actuel).
> Quand une affirmation a été **exécutée**, je le dis. Sinon, c'est une vérification par lecture.
> Je n'ai modifié aucun autre fichier.
>
> Gravités : **bloquant** (on ne peut pas tenir une promesse du DOC sans le régler d'abord) /
> **important** / **mineur** / **négligeable**.
> Familles : **(A)** vision et architecture des mods ; **(B)** bug existant, indépendant des mods.

---

## 1. Verdict global sur la critique

C'est une critique **sérieuse et globalement fiable**. Presque toutes les références `fichier:ligne`
sont exactes, à quelques lignes près. Les six bugs annoncés existent tous. J'en ai reproduit un en
l'exécutant, et deux sont même un peu plus graves que ce qu'elle dit. Elle respecte la plupart des
choix assumés du DOC : elle le dit elle-même quand elle ne conteste pas un point, par exemple « pas de
trieur » ou « pas de sandbox ».

Ses défauts :
1. **Inflation des gravités.** Elle classe 6 points « BLOQUANT ». À mon avis, 2 le sont vraiment : le
   point d'entrée unique pour rewind/fork/export, et le fait que la fin de tour vit dans les UI.
2. **Quelques affirmations fausses ou mal étayées.** « `main` vert repose sur l'humain » est faux : une
   CI lance pytest à chaque push et chaque PR sur `main`. Le lien avec TICKET-083 est erroné. La
   critique imagine aussi un serveur web multi-sessions qui n'existe pas.
3. **Des formules qui forcent le trait.** Elle écrit « sous-estimé d'un ordre de grandeur » alors que
   le DOC ne donne aucune estimation. Elle cite aussi un message de commit désobligeant, ce qui n'est
   pas un argument technique.

Le noyau de fond est juste : il vaut mieux **assainir le moteur actuel avant de construire le
chargeur de mods**. C'est la recommandation la plus utile du document.

---

## 2. Classement par ordre d'importance (points retenus)

| Rang | Point (§ critique) | Fam. | Verdict | Gravité révisée | À décider / à faire |
|---|---|---|---|---|---|
| 1 | Pas de point d'entrée unique pour rewind/fork/export ; 5 listes de tables tenues à la main (3.4, 3.6, 4.2, 5.2) | A | Pertinent (en partie déjà connu : TICKET-088/089) | **bloquant** pour §8 | Construire un « registre des données de save » dans le moteur actuel, **avant** les mods |
| 2 | Le tour est éclaté : la fin de tour (mémoire living, auto-canonize) vit dans les UI, avec deux algorithmes différents (3.1, 4.6) | A | Pertinent | **bloquant** pour « le tour est un mod » | Rapatrier la fin de tour dans `Session` (planificateur post-tour) |
| 3 | Rewind web/CLI : ChromaDB jamais rembobinée (3.4) | B | **Confirmé** (plus grave qu'annoncé) | important | Corriger maintenant : `Session.rewind` doit appeler `VectorMemory.rollback` |
| 4 | Réordonner la migration : faire d'abord les étapes « sans mods » (5.10) | A | Pertinent | important | Adopter l'ordre 0a→0e avant le chargeur |
| 5 | Tour non transactionnel : ~10 commits indépendants, écritures avant l'appel LLM (3.2, 4.1) | A | Partiellement pertinent (« bloquant » exagéré) | important | Mettre les écritures en tampon + un seul commit ; condition pour « isolation des plantages » |
| 6 | Tour échoué ou annulé → `user_input` orphelin + `turn_id` décalé (3.2) | B | **Confirmé par exécution** | important | Corriger maintenant (annuler l'incrément et supprimer l'intent si le tour échoue) |
| 7 | Modèle de données du noyau non défini ; la vraie API sera celle de `axiom-turn` (4.4, 3.12, 5.1) | A | Pertinent | important (décision) | Écrire le modèle noyau (Save, Step, Event_Log générique, stockage par mod) ; traiter `axiom-turn` comme une API publique |
| 8 | Contexte de mod traçable + contributions déclarées dans le manifeste (5.6, 5.7) | A | Pertinent | important | Adopter `ModContext` (tout ce qu'un mod enregistre passe par lui) ; manifeste déclaratif |
| 9 | Harnais de test « golden turn » (3.14, 5.9) | A | Partiellement pertinent (la CI existe) | important | Créer un faux LLM scripté + un état de base comparable, avant de découper `process_turn` |
| 10 | Patches globaux au processus vs « 1 save = 1 modpack » (4.3) | A | Partiellement pertinent | important (décision) | Trancher : un modpack par processus (redémarrage pour changer de modpack) |
| 11 | Patches « sur n'importe quelle fonction » : pièges Python ; proposer des trampolines (3.11, 5.4) | A | Partiellement pertinent | important | Points d'accroche déclarés + remplacement de `__code__` en secours ; interdire de patcher pendant un tour |
| 12 | Les 3 règles de combinaison ne couvrent pas tous les cas : sortie JSON, streaming, étapes dépendantes, fusion (3.5, 5.8) | A | Partiellement pertinent | important | Ajouter à l'API : champs de sortie structurée routés, filtre de flux ≠ filtre final, fonction de fusion par collecte, prompt en sections |
| 13 | Dépendances pip des mods (torch, chromadb…) (6.1) | A | Pertinent (angle mort du DOC) | important (décision) | Décider : mods « pur Python » au début + dépendances déclarées dans `mod.toml` |
| 14 | Schéma figé : pas de versions, `CHECK(difficulty IN …)`, tables créées paresseusement (3.7) | A | Pertinent | important | Retirer le CHECK ; version de schéma par mod ; exécuteur de migrations |
| 15 | Compile/décompile d'univers : les données de mods seraient perdues (3.8) | A | Pertinent | important | Hooks `compile/decompile/refresh_definition` par mod |
| 16 | Jobs de fond concurrents : course mémoire living ↔ rewind ; patch à chaud pendant un tour ; époques (3.9, 5.3) | A+B | Partiellement pertinent ; bug **probable** | important | « Époque » de session : un job refuse d'écrire si un rewind ou un chargement a eu lieu entre-temps |
| 17 | Gestionnaire de mods et mode sans échec hors du système de mods (4.5) | A | Partiellement pertinent (le DOC §9 prévoit déjà le mode sans échec) | important, peu coûteux | `--safe-mode` + `axiom mods list/enable/disable` dans le noyau |
| 18 | Config globale fermée : les clés inconnues sont effacées (3.10) | A | Pertinent | mineur→important | Section `[mods.<id>]` préservée par `load_config`/`save_config` |
| 19 | Modpack embarqué dans les archives `.axiomsave`/`.axiom` ; un univers peut exiger des mods (6.4) | A | Pertinent | important (plus tard) | Manifeste de modpack dans les exports |
| 20 | Désactivation « à chaud » illusoire pour le code Python (3.13) | A | Partiellement pertinent (le DOC dit déjà « si possible ») | mineur (décision) | Afficher « au prochain lancement » pour les mods avec du code |
| 21 | `fork_save --turn` copie les events planifiés tirés **après** le point de fork (3.6) | B | **Confirmé** | mineur | Filtrer `fired_turn_id <= turn_id` |
| 22 | `regenerate.py` remplace une consigne qui n'existe pas → JSON stocké dans les variantes (3.11) | B | **Confirmé par exécution** | mineur | Corriger la consigne ; enlever le JSON avant de stocker |
| 23 | `_RUNTIME_TABLES` oublie aussi `Item_Instances` et `Session_Lore` (ajout de l'arbitre, prolonge 3.6) | B | **Confirmé par lecture** | mineur | À ajouter à TICKET-089 |
| 24 | `_pending_correction` non rembobinée, état caché sur `self` (3.3) | B+A | Confirmé ; gravité exagérée | mineur | Remettre à `None` au rewind ; leçon d'API : un stockage de mod plus simple qu'un `self.x` |
| 25 | Hooks sur l'édition manuelle, les corrections et le canonize (6.7) | A | Pertinent | mineur | Événements `on_state_edited`/`on_narrative_edited` |
| 26 | Sémantique des variantes (régénération) pour les mods (6.6) | A | Partiellement pertinent | mineur | Décider : variantes purement textuelles |
| 27 | PyPI : « noyau seul » casse les utilisateurs de 0.2.0 (3.16) | A | Partiellement pertinent (conteste une décision, avec un argument nouveau) | mineur | Garder la décision, mais publier sous un nouveau nom ou avec un bump majeur |
| 28 | Créateur de mods par LLM : injection de consignes via le lore (6.3) | A | Partiellement pertinent | mineur (étape 4) | Montrer un diff + demander une confirmation avant d'activer un mod généré |
| 29 | Une seule priorité globale est trop grossière (3.17) | A | Partiellement pertinent | mineur | Prévoir `before/after/conflicts` dans le manifeste ; surcharge par emplacement plus tard |
| 30 | Utiliser `pluggy` (5.5) | A | Partiellement pertinent | mineur | À évaluer : couvre exclusif/collecte, mal adapté au « load order » utilisateur |
| 31 | Observabilité : inspecteur de prompt par mod, coût des hooks (6.8) | A | Partiellement pertinent | mineur | Utile pour déboguer ; pas prioritaire |
| 32 | Coût réel de la migration (3.15) | A | Partiellement pertinent | mineur (information) | Les chiffres sont justes ; la question du gel des features est à régler (décision 6) |
| 33 | Ids de mods namespacés, `provides`, hash de contenu (6.11, 6.12) | A | Pertinent | mineur | À prévoir dans le format `.axmod` dès la v1 (ça coûte peu) |
| 34 | Mods de données vs univers : doublon (6.5) | A | Partiellement pertinent | mineur | Règle : un mod de données s'applique à tous les univers ; l'univers gagne sur un conflit d'id |
| 35 | i18n et aide intégrée des mods (6.9, 6.10) | A | Pertinent | mineur | Emplacements « clés de traduction » et « entrées d'aide » dans les mods d'UI |
| 36 | Licence AGPL et store (6.2) | A | Partiellement pertinent | négligeable pour l'instant | À trancher avant d'ouvrir le store (étape 5) |

---

## 3. Détail point par point (même ordre)

### Rang 1 — Registre unique des données de save (3.4, 3.6, 4.2, 5.2) — (A) Pertinent, bloquant pour §8
- **Vérifié.** Cinq listes indépendantes :
  - `axiom/checkpoint.py:77-153` (rewind) ;
  - `axiom/saves.py:844-963` (`fork_save`) ;
  - `axiom/savestore.py:40-54` (`_DEFINITION_COPY`) ;
  - `axiom/savestore.py:470-493` (`_RUNTIME_COPY`) ;
  - `axiom/package.py:94-105` (`_RUNTIME_TABLES`).
  Elles sont désynchronisées. TICKET-088/089 le documentent déjà en partie. J'ai trouvé en plus que
  `_RUNTIME_TABLES` oublie aussi `Item_Instances` et `Session_Lore` (rang 23).
- Il y a en plus **deux chemins de rewind** avec des effets différents :
  - Qt : `workers/db_tasks.py:151-178`, avec backup automatique + rollback vectoriel chaîné dans
    `ui/tabletop_view.py:1012-1023` ;
  - web/CLI : `axiom/session.py:408-437`, **sans backup ni rollback vectoriel**.
- Le §8 du DOC promet un stockage « rembobiné / forké / exporté automatiquement ». C'est impossible
  tant que chaque table sait se rembobiner à sa façon.
- La proposition 5.2 (une politique déclarée par donnée : `events`, `versioned_kv`, table indexée par
  tour, `custom`) est bonne et directement réutilisable. Sa remarque sur les **snapshots par mod** est
  fine et exacte : `rebuild_state_cache` part du dernier snapshot (`axiom/events.py:236-248`), pris tous
  les 25 tours (`session.py:53,254`).
- Construire ce registre pour les features actuelles corrige au passage 088/089 et les rangs 3, 21 et 23.

### Rang 2 — La fin de tour vit dans les UI (3.1, 4.6) — (A) Pertinent, bloquant pour « le tour est un mod »
- **Vérifié.**
  - Qt appelle `distil_narrative_to_memory` (`workers/fact_worker.py:16,61`) à partir d'un tampon de
    textes, et fait l'auto-canonize (`ui/tabletop_view.py:802,1111-1124`).
  - Le web appelle `distil_turns_to_memory`, avec un rattrapage depuis l'`Event_Log` sur une fenêtre
    de 6 tours (`main_web.py:2669-2751`), et n'a pas d'auto-canonize.
  - La CLI ne fait ni l'un ni l'autre.
- On a donc bien deux algorithmes, ce qui viole la règle « une seule source de vérité » d'`ARCHITECTURE.md`.
- Un « mod de tour » ou une future UI tierce ne pourrait pas reproduire ce comportement. C'est un
  prérequis réel. C'est aussi un bon ménage, même sans mods.

### Rang 3 — Rewind web/CLI sans rollback ChromaDB (3.4) — (B) Confirmé, important
- `Session.rewind` (`axiom/session.py:408-437`) n'appelle jamais `VectorMemory.rollback`
  (`axiom/memory.py:482-501`). Le docstring de `CheckpointManager.rewind` précise que c'est « au
  caller » de le faire (`checkpoint.py:62-63`). Aucun appel n'existe dans `main_web.py:1815`,
  `main_web.py:1930` ni `axiom/cli/play.py:185`.
- **Plus grave qu'annoncé.** `embed_chunk` utilise un `uuid4` comme identifiant
  (`axiom/memory.py:238`). En rejouant un tour, on ne remplace donc pas l'ancien chunk : on en ajoute
  un **second**. Le RAG voit à la fois le « futur annulé » et le nouveau tour.
- L'édition de message web (`main_web.py:1930`) passe par le même rewind : chaque correction de
  message laisse une trace fantôme.
- Aucun ticket ne le couvre dans `PENDING.md` ni `DONE.md`.

### Rang 4 — Réordonner la migration (5.10) — (A) Pertinent, important
- L'étape 1 du DOC (« emballer tout dans axiom-legacy ») valide le chargeur mais pas l'architecture.
  Les étapes 0a→0e proposées (harnais, tour unifié, registre de données, transaction, config et
  schéma) ont de la valeur **même si le chantier mods s'arrête**.
- Elles réduisent aussi le risque de conflit avec le chantier Multiplayer, qui touche le tour.
- C'est la recommandation la plus rentable de la critique.

### Rang 5 — Transaction du tour (3.2, 4.1) — (A) Partiellement pertinent, important
- **Vérifié.** Les intents sont commités avant l'appel LLM (`axiom/arbitrator.py:230-236` →
  `append_event`). Il y a ensuite des commits séparés : Timeline (l.641), snapshot d'inventaire
  (l.716-717), modifiers (l.791), inventaire (l.796-797), etc. Le patron `_pending_events` existe déjà
  pour les events (l.229, 607).
- **Ce qui est exagéré :** « BLOQUANT ». L'isolation des plantages peut d'abord se faire au niveau de
  chaque appel de hook : on attrape l'exception et on ignore la contribution du mod, sans avorter le
  tour. Le demi-état n'apparaît que si l'exception remonte.
- Le vrai risque reste la corruption silencieuse d'une save. C'est donc important, mais ça peut se
  faire progressivement.

### Rang 6 — Tour échoué → `user_input` orphelin (3.2) — (B) Confirmé par exécution, important
- Reproduit avec un faux LLM qui lève `LLMConnectionError` : après l'échec, `turn_id == 1`, l'Event_Log
  contient `(1, 'user_input')` sans narration, et `_load_history()` renvoie le message utilisateur seul.
- **Cause :**
  - `self._turn_id += 1` a lieu **avant** `process_turn` (`axiom/session.py:209`) ;
  - l'intent est commité avant le LLM (`arbitrator.py:230-236`) ;
  - l'intent pool est vidé (l.212-213).
- Même chemin pour un `GenerationCancelled` (bouton « stop »). Au tour suivant, l'historique envoyé au
  LLM contient deux messages utilisateur d'affilée.
- Cela touche Qt, web et CLI, qui passent tous par `Session`.

### Rang 7 — Modèle de données du noyau ; `axiom-turn` = la vraie API (4.4, 3.12, 5.1) — (A) Pertinent, important
- Le §3.1 du DOC liste des mécanismes, mais aucune donnée.
- Le rewind est indexé par `turn_id` partout (`checkpoint.py`), et `resolve_point(at_turn | at_minute)`
  (`saves.py`) montre qu'il existe deux axes de temps.
- Il faut décider ce que le noyau connaît : un « pas » (step) générique, un Event_Log générique à
  réducteurs enregistrés, et peut-être les entités.
- L'analogie Fabric (petit Loader + « Fabric API » qui est un mod) est juste. Elle est compatible avec
  la décision « le tour est un mod », à condition de versionner `axiom-turn` comme une API publique.
- Ce n'est pas bloquant au sens strict : c'est **une décision à prendre avant l'étape 0**.

### Rang 8 — `ModContext` et manifeste déclaratif (5.6, 5.7) — (A) Pertinent, important
- Le DOC exige des patches « réversibles, visibles » et un écran de conflits.
- Si tout ce qu'un mod enregistre (hooks, emplacements, patches, threads, config, stockage) passe par
  un contexte, le retrait devient automatique au lieu de dépendre de la discipline de l'auteur. C'est
  crucial pour les mods écrits par LLM.
- Déclarer les contributions dans `mod.toml` permet de calculer les conflits **sans exécuter le code**.
  Ce sont des idées éprouvées (Obsidian, VS Code) qui servent directement le §9.

### Rang 9 — Harnais « golden turn » (3.14, 5.9) — (A) Partiellement pertinent, important
- **Vrai :** 1 029 fonctions de test (compté). Il existe plusieurs faux LLM ad hoc, mais pas de test
  de bout en bout « N tours → rewind → fork → export → comparaison d'état ». Ce harnais est le bon
  prérequis au découpage de `process_turn`, et il servira ensuite de `axiom mod test`.
- **Faux :** « la discipline `main` toujours vert repose sur l'humain ».
  `.github/workflows/tests.yml:10-12,86-93` lance pytest (3.11 et 3.12) à chaque push et chaque PR sur
  `main`. Seul le venv d'un agent n'avait pas pytest ; aujourd'hui, `.venv/bin/python -m pytest`
  fonctionne (pytest 9.0.3).

### Rang 10 — Patches globaux vs 1 save = 1 modpack (4.3) — (A) Partiellement pertinent, important (décision)
- **Juste :** un monkeypatch modifie tout le processus. Charger une save B après une save A, dans la
  même app Qt, suppose de retirer proprement les patches de A, ce qui rejoint le rang 20.
- **Exagéré :**
  - Il n'y a pas de « conflit interne à la vision ». Le DOC ne parle pas de deux saves actives en même
    temps.
  - Le web n'a qu'**une** session active (`ACTIVE_SESSION` global, `main_web.py:54`).
  - Le serveur multi-sessions et le multijoueur réseau sont hors périmètre.
  - Lister ou prévisualiser des saves n'exige pas de charger leurs mods.
- **Nuance utile :** si fork/export appellent des hooks `on_fork/on_export` des mods (rang 1), il faut
  que le modpack de la save concernée soit chargé.
- L'option « un modpack par processus » est simple et cohérente avec le §2. C'est à acter.

### Rang 11 — Pièges des patches Python ; trampolines (3.11, 5.4) — (A) Partiellement pertinent, important
- **Vérifié :**
  - 109 imports `from axiom…` au niveau module et 197 imports locaux ;
  - `from axiom.rules import RulesEngine` (`arbitrator.py:36`) ;
  - `from axiom.prompts import HISTORY_TURN_CAP` (`session.py:32`) ;
  - instances créées une seule fois (`arbitrator.py:145-147`).
  Remplacer `module.f = wrapper` ne marche donc pas partout.
- **Nuance :** remplacer `f.__code__`, que la critique cite elle-même en secours, fonctionne quel que
  soit le style d'import pour les fonctions Python pures. Le « pas sans préparation » est donc un peu
  fort pour les fonctions. Il reste exact pour les constantes, les classes et les callbacks déjà remis.
- La recommandation est bonne : points d'accroche nommés d'abord, `__code__` en secours documenté, pile
  figée pendant un tour.

### Rang 12 — Règles de combinaison incomplètes (3.5, 5.8) — (A) Partiellement pertinent, important
- **Juste et concret :**
  1. **Sortie JSON unique partagée.** Un mod « faim » doit **contribuer** un champ au schéma et
     **recevoir** sa valeur parsée : c'est un motif « contribution + routage ».
  2. **Streaming.** Le filtre à tampon de 15 caractères (`arbitrator.py:890-913`) rend impossible une
     « chaîne » token par token pour la traduction : il faut distinguer filtre de flux et filtre du
     texte final.
  3. **Étapes dépendantes.** Le RAG nourrit la détection des entités (`arbitrator.py:315`, `:1062`),
     qui filtre ensuite les faits et croyances.
- Le prompt en sections positionnées (`build_narrative_prompt` a plus de 18 paramètres) est une bonne
  forme pour la « collecte » de prompt.
- **Moins convaincant :**
  - Le « 5ᵉ motif pub/sub » est une collecte sans résultat, ou un simple hook.
  - « Choisir la fonction de fusion » est raisonnable, mais ce n'est pas un trou : le créateur de
    l'emplacement choisit déjà sa règle (§6).
- Ce sont des précisions d'API, pas des défauts de vision.

### Rang 13 — Dépendances pip des mods (6.1) — (A) Pertinent, important (décision)
- Vrai angle mort du DOC. `pyproject.toml:35-43` embarque `chromadb` et `sentence-transformers`
  (donc torch). Un `.axmod` en zip ne peut pas porter de roues natives.
- TICKET-070 (torch sous Windows) montre que c'est coûteux.
- Il faut une réponse avant d'extraire la mémoire en mod.

### Rang 14 — Schéma figé, pas de migrations versionnées (3.7) — (A) Pertinent, important
- **Vérifié :**
  - `CHECK(difficulty IN ('Normal','Hardcore','Companion','Multiplayer'))` (`axiom/schema.py:128`) ;
  - une migration dédiée a été nécessaire pour l'étendre (`migrate_saves_difficulty_constraint`,
    `schema.py:1202`) ;
  - pas de `user_version` ;
  - des `ensure_…` paresseux (`schema.py:509-570`).
- Un mod qui ajoute un mode de jeu devrait reconstruire `Saves`.
- Il faut une version de schéma par mod, stockée dans la save, pour le cas « mod réactivé après N
  versions » (§8 : données en sommeil).

### Rang 15 — Compile/décompile d'univers (3.8) — (A) Pertinent, important
- **Vérifié :**
  - `_parse_tree` renvoie un dict fermé (`axiom/compile.py:520-538`) ;
  - seul `[extra]` passe tel quel (l.204-206) ;
  - `[calendar]` et `[companion]` sont parsés en dur (l.182-202).
- Un mod de données d'univers serait ignoré, et l'aller-retour sans perte d'Universe-as-Code casserait.
- Il faut des hooks de compilation par mod dès que « temps » ou « companion » deviennent des mods.

### Rang 16 — Concurrence des jobs de fond (3.9, 5.3) — (A) Partiellement pertinent + (B) probable, important
- **Vérifié par lecture :** le job living web est un `threading.Thread` daemon
  (`main_web.py:2751`) qui lit `turn`, puis appelle le LLM (plusieurs secondes), puis écrit
  Facts/Observations **sans `ACTIVE_SESSION_LOCK`** (l.2685-2745).
- Un rewind pendant ce délai laisse des faits pour des tours annulés. Au rejeu, ils sont suivis de
  doublons.
- **Bug probable**, non testé : c'est une course, donc difficile à reproduire à coup sûr.
- **Faux :** « TICKET-083 est une variante du même problème ». 083 porte sur `created_turn_id = min(...)`
  des croyances, pas sur un thread.
- Le risque « patch à chaud pendant un tour » est juste. Les « époques de session » (5.3) sont une
  solution simple et générique.

### Rang 17 — Mode sans échec hors du système de mods (4.5) — (A) Partiellement pertinent, important et peu coûteux
- Le DOC §9 exige déjà un mode sans échec. L'apport réel est une conséquence : si **toutes** les UI
  sont des mods, il faut un moyen de désactiver un mod **sans UI**, par un flag de lancement ou une
  commande CLI du noyau.
- Ce n'est pas bloquant, mais c'est à inclure dès l'étape 0 : ça coûte peu et c'est fatal si on l'oublie.

### Rang 18 — Config fermée (3.10) — (A) Pertinent, mineur→important
- **Vérifié :** `load_config` ne garde que les clés connues (`axiom/config.py:319-322`) et `save_config`
  réécrit `asdict(config)` (l.362-366).
- Une clé de mod est donc effacée à la première sauvegarde des réglages.
- La correction est simple : une section `mods` préservée telle quelle.

### Rang 19 — Modpack dans les archives et exigences des univers (6.4) — (A) Pertinent, important plus tard
- Le §8 enregistre le modpack dans la save, mais rien ne dit que `.axiomsave` (`savestore.pack_save`)
  et `.axiom` (`package.pack_universe`) le transportent.
- Sans ça, une save partagée est inutilisable pour qui la reçoit. Ça coûte peu à prévoir dans le format.

### Rang 20 — Désactivation à chaud (3.13) — (A) Partiellement pertinent, mineur (décision)
- Techniquement juste : Python ne décharge pas proprement un module.
- Mais le DOC écrit déjà « à chaud **si possible** ». La critique précise ce que « possible » veut dire.
  Ce n'est pas une contradiction.
- Avec le rang 8 (`ModContext`), les hooks et les données peuvent être retirés à chaud. Le code
  arbitraire et les patches sont retirés au prochain lancement.

### Rang 21 — `fork_save` : events planifiés tirés après le fork (3.6) — (B) Confirmé, mineur
- `axiom/saves.py:947-957` copie tous les `Fired_Scheduled_Events` sans filtrer `fired_turn_id <= turn_id`.
  Pourtant la colonne existe justement pour ça (TICKET-075, cf. le rewind `checkpoint.py:148-151`).
- Accessible via `axiom saves fork --turn N` (`axiom/cli/saves_cmd.py:234`). `duplicate_save`
  (`savestore.py:745`) forke sans point, donc sans effet.
- Le second grief (modifiers « présents » plutôt que ceux du tour du fork) est **déjà assumé** dans le
  docstring (« modifiers are copied as-is », `saves.py:856`) et relève de TICKET-088
  (`Modifier_Snapshots` non copiés).
- Même défaut pour `Session_Lore` (copie sans filtre sur `origin_turn`, l.920-930).

### Rang 22 — `regenerate.py` : remplacement sans effet (3.11) — (B) Confirmé par exécution, mineur
- J'ai exécuté `build_narrative_prompt` : la chaîne `"You MUST end your response with a JSON block"`
  est absente, alors que la consigne `~~~json` est bien présente (`axiom/prompts.py:57`). Le `.replace`
  de `regenerate.py:73-79` ne fait donc rien.
- Le texte régénéré, JSON compris, est stocké tel quel (`regenerate.py:103`). Qt
  (`ui/widgets/chat_display.py:84`) et le web (`web/app.js:1516`) le masquent à l'affichage.
- En revanche, il repart tel quel dans l'historique envoyé au LLM (`regenerate.py:36`,
  `Session._load_history`). Impact modéré.
- L'autre constat est aussi exact : la régénération se fait sans stats, sans RAG, sans lore
  (`regenerate.py:60-70`). Un hook « avant le prompt » ne s'y appliquerait pas.

### Rang 23 — `_RUNTIME_TABLES` incomplet (ajout de l'arbitre) — (B) Confirmé par lecture, mineur
- En plus de Facts/Observations/Mental_Models (TICKET-089), `axiom/package.py:94-105` oublie
  `Item_Instances` et `Session_Lore`.
- La purge se fait avec `PRAGMA foreign_keys=OFF` (`package.py:123`). Il n'y a donc pas de cascade
  depuis `Saves`, et ces lignes de partie restent dans une archive « définition seule ».
- Même classe que TICKET-089 : à y ajouter.

### Rang 24 — `_pending_correction` et état caché (3.3) — (B) Confirmé, mineur ; (A) leçon valable
- `arbitrator.py:152,450,465,1731-1734` : le texte d'indice « l'action a échoué » vit sur `self`. Rien
  ne le remet à zéro au rewind (`session.py:415` appelle `invalidate_stats_cache`, un no-op,
  `arbitrator.py:166-176`).
- Après un rewind, un indice issu d'un tour annulé peut s'injecter une fois. C'est une gêne mineure,
  pas une corruption.
- Les variables par tour posées sur `self` (l.218-227) rendent le moteur non réentrant. C'est vrai, mais
  sans conséquence tant qu'il n'y a qu'un tour à la fois.
- La leçon d'API est juste : le stockage de mod doit être plus simple à utiliser qu'un `self.x`.

### Rang 25 — Hooks sur les éditions hors tour (6.7) — (A) Pertinent, mineur
- L'éditeur de saves, l'édition de message (`main_web.py:1935-1972` : `update_event_payload` +
  `update_turn_narrative`), le Studio et le canonize modifient l'état hors tour.
- Un mod qui indexe la narration doit en être notifié.

### Rang 26 — Variantes et mods (6.6) — (A) Partiellement pertinent, mineur
- Vrai : `append_variant` fait un `UPDATE` sur `Event_Log` (`regenerate.py:125-131`).
- Mais c'est le modèle « multivers » voulu (TICKET-011, `DONE.md:229`). « Contredit l'append-only » est
  donc un reproche à un choix existant.
- Il faut seulement une phrase d'API : « une variante est purement textuelle, les mods ne sont pas
  rappelés ».

### Rang 27 — PyPI (3.16) — (A) Partiellement pertinent, mineur
- Conteste en partie une décision actée (§11), mais avec un argument technique nouveau :
  `axiom/__init__.py:19` exporte `Session` et `Universe`, et l'aide documente `take_turn`.
- La version 0.2.0 est en bêta, donc la casse est limitée. La décision « PyPI = noyau seul » peut
  rester ; il faut seulement choisir entre un nouveau nom et un bump majeur.

### Rang 28 — Créateur LLM et injection de consignes (6.3) — (A) Partiellement pertinent, mineur (étape 4)
- Ne remet pas en cause « pas de sandbox ». Il signale un cas distinct : du code que l'utilisateur
  **n'a pas choisi**, dicté par du contenu importé (lore, fiches SillyTavern).
- La mitigation (diff + confirmation) est légère et compatible avec le §2. À noter pour l'étape 4.

### Rang 29 — Priorité unique (3.17) — (A) Partiellement pertinent, mineur
- Les contraintes `before/after/conflicts` dans le manifeste coûtent peu et évitent un trieur externe.
- La surcharge par emplacement peut attendre un vrai besoin.

### Rang 30 — `pluggy` (5.5) — (A) Partiellement pertinent, mineur
- `pluggy` est solide, mais son ordre d'appel est fixé par l'ordre d'enregistrement et par
  `tryfirst/trylast`, pas par un « load order » utilisateur.
- `firstresult` n'est pas exactement « exclusif avec gagnant désigné ».
- À évaluer comme brique interne, pas à adopter d'office.

### Rang 31 — Observabilité (6.8) — (A) Partiellement pertinent, mineur
- Cohérent avec l'exigence « visibles » du §5. Un inspecteur de prompt par mod est un bon mod
  d'outillage (§9), pas une obligation du noyau.

### Rang 32 — Coût de la migration (3.15) — (A) Partiellement pertinent, mineur (information)
- **Chiffres vérifiés :**
  - `main_web.py` fait 144 707 octets et `web/app.js` 190 993 ;
  - 40 accès à `ACTIVE_SESSION._db_path` et 26 à `._save_id` ;
  - `_last_lore_hits` est posé de l'extérieur (`main_web.py:2947`).
- « Sous-estimé d'un ordre de grandeur » est un homme de paille : le DOC ne donne aucune estimation.
- La seule question utile est celle du gel des features (décision 6).

### Rang 33 — Ids namespacés, `provides`, hash (6.11, 6.12) — (A) Pertinent, mineur
- Ça ne coûte rien à mettre dans le format v1. Ce sera très coûteux à changer une fois le store ouvert.

### Rang 34 — Mods de données vs univers (6.5) — (A) Partiellement pertinent, mineur
- Il suffit d'une règle de fusion.

### Rang 35 — i18n et aide (6.9, 6.10) — (A) Pertinent, mineur
- L'i18n vit côté app (`core/localization.py`, 10 locales). L'aide est un registre centralisé
  (`ui/help_system.py`).
- Ce sont des emplacements à prévoir dans les mods d'UI, pas dans le noyau.

### Rang 36 — AGPL et store (6.2) — (A) Partiellement pertinent, négligeable pour l'instant
- Vrai : le projet est sous AGPL-3.0 (`pyproject.toml:19`).
- C'est une question juridique qui ne concerne que l'étape 5 (le store).

---

## 4. Points écartés (mauvaise foi, erreur ou hors sujet)

| Affirmation | Pourquoi je l'écarte |
|---|---|
| « La discipline `main` toujours vert repose sur l'humain » (3.14) | **Faux** : la CI `.github/workflows/tests.yml` lance pytest sur push et PR vers `main`. |
| « TICKET-083 est une variante temporelle » de la course du job living (3.9) | **Faux** : 083 concerne le calcul de `created_turn_id` des croyances, pas la concurrence. |
| « Le serveur web pourra servir plusieurs sessions » + multijoueur réseau, cités comme preuves du conflit 4.3 | **Spéculation présentée comme argument** : aujourd'hui il y a une seule `ACTIVE_SESSION`, et le réseau est hors périmètre v1. Le fond (4.3) est retenu, mais pas ces preuves. |
| Étiquette « BLOQUANT » sur 4.1, 4.3, 4.4, 4.5 | **Inflation** : ce sont des décisions ou des travaux importants, pas des empêchements. Seuls 4.2 et 4.6 bloquent vraiment une promesse du DOC. |
| « Coût sous-estimé d'un ordre de grandeur » (3.15) | **Homme de paille** : le DOC ne chiffre rien. |
| Citation du commit `1f48c82` (« …shitty update ») pour la question du gel (§7 q.5) | **Hors sujet / ad hominem** : la question de la propriété des fichiers pendant la refonte est valable (décision 6), l'argument ne l'est pas. |
| « `regenerate` contredit l'append-only » (6.6) | Reproche adressé à un choix existant et volontaire (multivers, TICKET-011). Seule la question de sémantique pour les mods est retenue. |
| « Cinquième motif pub/sub » (3.5.6) | Un abonnement sans résultat est une collecte, ou un hook simple. Il n'y a pas de nouveau motif à nommer. |

Les « atouts » du §2 de la critique sont exacts (vérifiés : `events.py:533` ignore bien les types
inconnus au replay ; `take_turn_multiplayer` est bien branché sur `resolve_tick`). Je ne les classe pas :
ce ne sont pas des problèmes.

---

## 5. Décisions à prendre par le propriétaire

J'ai filtré les 12 questions de la critique. J'en garde 9 qui méritent vraiment une décision
maintenant ou bientôt.

**Décision 1 — Corriger les bugs trouvés tout de suite, hors chantier mods ?**
- Options : (a) oui, en tickets normaux ; (b) attendre la refonte.
- **Recommandation : (a).** Surtout le rewind ChromaDB (rang 3) et le tour échoué orphelin (rang 6),
  qui touchent les joueurs aujourd'hui. Les trois petits bugs (rangs 21, 22, 23) sont des corrections
  d'une ligne. Ça assainit le terrain avant de concevoir le registre de données.

**Décision 2 — Dans quel ordre travailler ?**
- Options : (a) l'ordre du DOC (noyau de mods d'abord) ; (b) d'abord « assainir le moteur » : harnais
  de test, fin de tour dans le moteur, un seul rewind, registre des données de save, transaction ;
  **ensuite** le chargeur de mods.
- **Recommandation : (b).** Chaque étape est utile même si les mods n'aboutissent jamais. Et c'est
  exactement le futur « stockage de save » du noyau, testé sur de vraies features.

**Décision 3 — Que connaît le noyau ?** (le noyau doit-il savoir ce qu'est un « tour », une entité, une stat ?)
- Options : (a) rien, tout est dans le mod de tour ; (b) un « pas » générique (step) + un journal
  d'événements générique, avec entités et stats dans un mod de base « monde » ; (c) entités et stats
  dans le noyau.
- **Recommandation : (b).** Il faut une unité de temps pour rembobiner. « Step » garde la possibilité
  d'utiliser Axiom pour autre chose que du JDR. Assumer que le mod `axiom-turn` est **l'API publique**
  des auteurs de mods (façon Fabric API), avec sa propre version.

**Décision 4 — Changer de modpack : faut-il redémarrer ?**
- Options : (a) un modpack par processus : ouvrir une save avec d'autres mods = relancer le moteur ;
  (b) des mods chargés par session.
- **Recommandation : (a).** C'est simple, cohérent avec « pas de garantie », et c'est ce que font les
  lanceurs Minecraft (une instance = un modpack).

**Décision 5 — « Désactiver à chaud » : jusqu'où ?**
- Options : (a) tout à chaud ; (b) à chaud pour les données et les hooks, « au prochain lancement »
  pour les patches et le code arbitraire.
- **Recommandation : (b)**, affiché clairement dans la liste à cocher. C'est ce que le « si possible »
  du DOC veut dire en pratique.

**Décision 6 — Qui touche au tour de jeu pendant la refonte ?**
- Options : (a) gel des nouvelles features qui touchent le tour (`arbitrator.py`, `session.py`) pendant
  le découpage ; (b) pas de gel, avec un propriétaire unique de ces fichiers ; (c) rien.
- **Recommandation : (b)**, formalisé dans `maintenance/collab/` : une personne possède
  `arbitrator.py`/`session.py` pendant le découpage, et l'autre passe par elle. Le chantier Multiplayer
  touche aussi le tour : le finir ou le geler avant l'étape « découper le tour ».

**Décision 7 — Mods qui ont besoin de bibliothèques lourdes (torch, chromadb…) ?**
- Options : (a) mods « pur Python » uniquement au début, les grosses dépendances restant installées
  avec Axiom ; (b) chaque mod déclare ses dépendances pip, installées dans l'environnement commun ;
  (c) un environnement Python par modpack.
- **Recommandation : (a) maintenant, (b) plus tard.** Prévoir le champ dans `mod.toml` dès la v1, mais
  ne pas écrire d'installeur tant que le store n'existe pas. (c) est trop lourd, surtout sous Windows.

**Décision 8 — Paquet PyPI**
- Options : (a) `axiomai-engine` devient le noyau seul, avec un bump de version majeur ; (b) un nouveau
  nom pour le noyau (`axiomai-kernel`) et `axiomai-engine` = noyau + mods de base.
- **Recommandation : (b)** si des utilisateurs de la bêta existent vraiment, sinon (a). L'esprit de
  la décision actée (« PyPI = noyau ») est respecté dans les deux cas.

**Décision 9 — Plus tard, avant le store : un univers peut-il exiger des mods, et quelle licence pour les mods ?**
- Recommandation :
  - un univers peut **recommander** un modpack, déclaré dans son manifeste ;
  - les exports de save embarquent la liste des mods ;
  - la licence (AGPL imposée ou non) se tranche avec un avis juridique avant l'étape 5.
- Pas urgent.

Questions de la critique que je n'ai **pas** retenues comme décisions :
- la sémantique des variantes : il suffit d'écrire « variantes = texte seulement » ;
- la priorité unique ou par emplacement : on commence par l'ordre global + `before/after` dans le
  manifeste ;
- « qu'est-ce qu'un tour » : c'est couvert par la décision 3.
