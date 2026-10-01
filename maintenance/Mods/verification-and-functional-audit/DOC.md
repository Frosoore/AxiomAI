# DOC — Vérification, Audit Fonctionnel et Déconnexion Complète des Mods

## 1. Objectif
Garantir que le système de mods respecte deux principes fondamentaux :
1. **Déconnexion absolue du core** : Le noyau (`axiom/`, `core/`) et les applications hôtes ne doivent pas conserver de code rémanent, de doublons masqués ou de fallbacks exécutant la logique métier en sous-main si le mod est désactivé.
2. **Effectivité fonctionnelle réelle** : Chaque mod doit avoir un impact tangible, prouvé et mesurable sur le système (narratif, persistance, état, UI, génération). Aucun mod ne doit être une coquille vide, un no-op ou du code obsolète hérité de refactorings passés.

## 2. Principes de Déconnexion Appliqués
- **Isolation du noyau headless (`axiom/arbitrator.py`)** :
  - `axiom.world` : en présence du `KernelRegistry`, toute mutation et exécution de règles dépend exclusivement du hook `axiom.step:arbitrate_mutations`. Le core n'exécute aucun fallback métier.
  - `axiom.time` : si le service `time` n'est pas enregistré, `ctx.elapsed_minutes` reste à 0 et `ctx.new_time == ctx.total_mins`. Le Timekeeper LLM n'est pas appelé et aucune hypothèse de rythme n'est injectée.
  - `axiom.living_memory` : si le service `living_memory` n'est pas présent, aucune table de faits, croyances ou modèles mentaux n'est requêtée par l'arbitre.
- **Isolation de la session (`axiom/session.py`)** :
  - `axiom.rag` : `Session._vector_memory` reste `None` si le mod `axiom.rag` est désactivé ou absent du registre.
  - `core.stat_dynamics` : `ensure_stat_dynamics` n'est invoqué que si le mod est activé.
  - Chargement dynamique : `Session` s'appuie désormais sur `bootstrap_all_mods(config=cfg)` pour charger l'intégralité des mods découverts et ordonnés selon le DAG.
- **Protection de l'hôte Web (`main_web.py`)** :
  - Les routes API `/api/memory/*` et `/api/session/turn` respectent l'état activé/désactivé des mods.
  - L'installation depuis le store (`/api/store/install`) respecte la cible demandée sans écraser les sources de mods du dépôt.

## 3. Effectivité Démontrée des Mods
- Tous les mods installés déclarent et enregistrent des contributions réelles :
  - `axiom.turn` : pipeline de tour, slot `prompt_sections`, filtres de stream et de narration finale.
  - `axiom.world` : persistance du monde, slots de types d'entités et règles personnalisées, hook d'arbitrage de mutations.
  - `axiom.time` : calendrier, service temporel public, slot `prompt_sections`, hook `after_step` avec déclenchement d'événements planifiés et simulation Chronicler.
  - `axiom.inventory` : structure hiérarchique d'équipement, slot `prompt_sections`, actions d'inventaire.
  - `axiom.rag` : indexation vectorielle et réinjection contextuelle.
  - `axiom.living_memory` : extraction incrémentale de faits, croyances et modèles mentaux, slot `prompt_sections`.
  - `axiom.illustrations` : génération d'illustrations contextuelles et analyse de scène.
  - `core.stat_dynamics` : calcul des dynamiques passives (décroissance, régénération, points de repos) et gestion des modificateurs temporaires.
  - `axiom.help_system` : documentation contextuelle, aide interactive et commandes CLI d'aide.
  - `axiom.sillytavern` : importation de personnages SillyTavern / PNG chunks et conversion vers entités Axiom.
  - `community.survival` : surveillance de la fatigue et de l'effort, guidelines de survie injectées dans le prompt et consignation d'épuisement dans la Timeline.

## 4. Gating et Cycle de Vie des Interfaces Frontend
- **Frontends as Mods (Pilier D4 & §9)** :
  - `axiom.ui.qt` : contrôle le lancement de l'application de bureau native PySide6. Si désactivé, `main.py` bloque le démarrage et invite à réactiver le mod ou basculer sur l'interface Web. La désactivation in-app depuis `ModsDialog` sollicite une confirmation explicite puis termine le processus.
  - `axiom.ui.web` : contrôle le serveur HTTP et la SPA locale. Si désactivé, `main_web.py:run_server()` refuse l'écoute réseau.
  - `axiom.cli` : contrôle la boucle de jeu dans le terminal. Si désactivé, `axiom play` refuse l'exécution de la partie.
- **Instanciation de widgets par slots** :
  - `axiom.ui.qt:sidebar_widget` et `axiom.ui.qt:settings_tab` acceptent directement des classes `QWidget` (ainsi que les tuples `(titre, widget)` et dictionnaires) pour permettre aux extensions tierces d'enrichir la barre latérale et les paramètres sans modification du code de l'interface bureau.

## 5. Assainissement des Doublons, Emplacements Canoniques et Éradication de `/ui`
- **Éradication complète du dossier `/ui`** :
  - Conformément à l'architecture modulaire pure ("UI as a mod"), l'ensemble des fichiers Python de l'interface bureau native a été déplacé sous `mods/axiom.ui.qt/ui/`.
  - Aucun fichier Python ne réside désormais à la racine de `/ui` (répertoire supprimé).
- **Emplacements canoniques par mod** :
  - `mods/axiom.inventory/ui/inventory_view.py` : vue de l'inventaire.
  - `mods/axiom.time/ui/timeline_view.py` : vue de la chronologie / calendrier.
  - `mods/axiom.living_memory/ui/mental_models_widget.py` et `memory_browser.py` : exploration de la mémoire vivante.
  - `mods/axiom.help_system/ui/help_system.py` et `help_dialogs.py` : système d'aide contextuelle, infobulles, explorateur de documentation et visites guidées.
- **Façade de découplage à coût nul intégrée** :
  - Les gardes `is_help_system_enabled()` sont intégrés nativement au sein de `mods/axiom.help_system/ui/help_system.py` et `help_dialogs.py`. Lorsque le mod est désactivé, `doc()` et `doc_tab()` opèrent en no-op immédiat sans coût mémoire ni attachement d'événements, rendant tout shim intermédiaire obsolète.
- **Support des imports modulaires pointillés (`mods/__init__.py`)** :
  - Le finder `_DottedModFinder` installe `ModuleSpec` avec `spec.has_location = True` et renseigne `spec.origin`, garantissant la présence native de `__file__` sur tous les modules de mods.


