# Plan d'attaque : Feature Multijoueur Simultané

> Plan d'origine (rédigé via Gemini CLI), collé **verbatim** ci-dessous.
> **Implémentation : Claude Code.** Les révisions issues de la vérification réf-par-réf (2026-06-26)
> sont en tête ci-dessous ; le corps reste le plan d'origine pour traçabilité.

---

## RÉVISIONS APRÈS VÉRIFICATION (Claude, 2026-06-26)

Vérifié chaque réf `fichier:ligne` par grep contre le code réel. Le plan est **validé sur le fond** ;
toutes les fonctions/variables citées existent. Décisions et corrections actées avec l'utilisateur :

**Décisions :**
- **Implémenteur : Claude** (pas Gemini) → déclaration dans `collab/claude/EN_COURS.md`, dossier d'étape
  `maintenance/Multiplayer/` (pas `features/feature-multiplayer/`).
- **Portée spatiale v1 = simple** : on garde un « joueur primaire » pour le focus existant et on **ajoute**
  les positions des autres joueurs + les PNJ co-localisés. Pas de réécriture complète de l'arbitre.
- **Disponibilité = toujours** : `Multiplayer` toujours proposé au menu (le flux « créer la save puis ajouter
  les joueurs au Studio » interdit de conditionner à « ≥2 joueurs » à la création).

**Corrections obligatoires avant code :**
1. **§1 Schéma — garde-fou de migration.** `_DDL_SAVES` est bien à `schema.py:80`. La fonction
   `migrate_saves_difficulty_constraint` (`schema.py:776`) court-circuite à la ligne **793**
   `if "'Companion'" in sql: return`. Comme toutes les bases existantes ont déjà `Companion`, elles
   seraient considérées « à jour » et `Multiplayer` planterait la contrainte CHECK. → changer la garde
   pour tester `'Multiplayer'` (ligne 793) + adapter le message de log (ligne 826).
2. **§2A Prompts — bons emplacements.** Règle protagoniste à `prompts.py:747` ; rappels « traduire I→You »
   aux lignes **846-848** (le plan disait « ~845 ») — à brancher aussi pour `Multiplayer`. `actors_str`
   existe déjà.
3. **§2B Arbitre — cible élargie (mais v1 simple).** ⚠ La méthode s'appelle en réalité
   **`_identify_relevant_entities`** (le plan disait `_fetch_relevant_entities`), `arbitrator.py:829`.
   L'hypothèse « un seul `player_entity_id` » est aussi à `arbitrator.py:209-210` (heuristique), 264-277
   (focus terms), 338-354, 534 (annotation timeline). v1 : on n'y touche pas, on ajoute juste les
   positions des autres joueurs dans `_fetch_relevant_entities` + PNJ co-localisés.
4. **§4 GUI — cible manquante : `workers/narrative_worker.py`.** Aujourd'hui `_on_send_message`
   (`tabletop_view.py:558`) construit un `PlayerAction` unique (590) et `NarrativeWorker` prend
   `action: PlayerAction` → `Session.take_turn()` (solo). Passer « le dict complet au NarrativeWorker »
   **exige d'étendre `NarrativeWorker`** pour accepter des intents multiples et appeler
   `take_turn_multiplayer`. `PlayerAction` reste un simple conteneur (réutilisé aussi en regenerate, l.741).
5. **§5 setup_view — deux endroits.** Le combobox de difficulté est construit à `setup_view.py:420-423`
   (statique) **et** `586-590` (où `Companion` est conditionné par `companion_mode_enabled`). Ajouter
   `Multiplayer` **aux deux**, sans condition.

**À réconcilier (sur feu vert, jamais de suppression sans accord) :** l'ancienne plomberie FIFO
`axiom/multiplayer.py::ActionQueue` + `core/multiplayer_queue.py::ArbitratorWorker` est contournée par
cette approche (NarrativeWorker). Vérifier si elle est devenue morte → proposer son retrait séparément.

---

Voici le plan d'attaque détaillé pour l'implémentation du mode Multijoueur simultané, inspiré directement
de la structure d'accumulation d'intentions et de résolution globale du Mode Companion.

---

## Objectif

Permettre à plusieurs personnages joueurs (entités de type `player` gérées localement) d'agir dans le
même tour. Leurs actions sont accumulées, puis résolues simultanément en un seul Tick de l'arbitre
principal, produisant une narration unique et cohérente à la troisième personne.

---

## 1. Base de données & Migrations de Schéma

Nous devons autoriser la valeur `'Multiplayer'` dans la contrainte de difficulté de la table `Saves`.

- **Fichier cible : `schema.py`**
  - Modifier le DDL `_DDL_SAVES` :
    `difficulty TEXT NOT NULL CHECK(difficulty IN ('Normal', 'Hardcore', 'Companion', 'Multiplayer'))`
  - Mettre à jour la fonction de migration pour qu'elle détecte si la contrainte SQLite contient bien
    `'Multiplayer'`. Si ce n'est pas le cas, elle exécutera la migration automatique (reconstruction
    propre de la table `Saves` par table temporaire) comme elle le fait actuellement pour `'Companion'`.

---

## 2. Adaptation du Moteur de Narration & Prompts

### A. Narration à la troisième personne pour tous les joueurs

En mode multijoueur, le narrateur ne doit pas s'adresser à un joueur unique en disant "Vous" (ce qui
créerait de la confusion entre les participants), mais narrer les actions de tout le groupe à la
troisième personne.

- **Fichier cible : `prompts.py` (`build_narrative_prompt`)**
  - Adapter les règles du narrateur lorsque `mode == "Multiplayer"` :
    - Remplacer la règle du protagoniste unique par :
      ```python
      if mode == "Multiplayer":
          rules.append(f"- Protagonists: The human players are {actors_str}. Describe their actions "
                       f"in the third person using their names, and do NOT use 'You' to refer to a single player.")
      else:
          rules.append(f"- Protagonist: '{player_id}' is the Human Player. Always address them as "
                       f"'You' and center the narrative around their actions.")
      ```
    - Adapter les rappels de fin de prompt (vers la ligne 845) pour ajuster l'instruction de
      traduction (ne pas traduire `"I"` en `"You"`, mais vers la troisième personne pour chaque acteur).

### B. Gestion des localisations multiples pour la pertinence (RAG / NPCs)

Si les joueurs se séparent dans différentes pièces ou zones de la carte, le moteur doit être conscient de
l'ensemble de leurs localisations pour charger le contexte spatial et les NPCs présents.

- **Fichier cible : `arbitrator.py` (`_fetch_relevant_entities`)**
  - Au lieu de ne lire que la position d'un seul `player_entity_id`, boucler sur l'ensemble des IDs
    d'acteurs ayant soumis une intention pour ce tour afin de collecter toutes leurs localisations.
  - Inclure dans le contexte les NPCs se trouvant à la position de n'importe quel joueur actif.

---

## 3. Session du Moteur (`Session`)

Pour éviter de surcharger `take_turn` (conçu pour le solo/compagnon), nous allons proposer une méthode
propre à la résolution multijoueur.

- **Fichier cible : `session.py`**
  - Ajouter une méthode `take_turn_multiplayer` :
    ```python
    def take_turn_multiplayer(
        self,
        intents: dict[str, str],
        *,
        on_token: Callable[[str], None] | None = None,
        on_status: Callable[[str], None] | None = None,
        temperature: float = 0.7,
        top_p: float = 1.0,
        verbosity_level: str = "balanced",
    ) -> ArbitratorResult:
        """Resolve a multiplayer turn with all player intents simultaneously."""
        self._intent_pool.clear()
        for pid, text in intents.items():
            self.submit_intent(pid, text)

        return self.resolve_tick(
            on_token=on_token,
            on_status=on_status,
            temperature=temperature,
            top_p=top_p,
            verbosity_level=verbosity_level,
        )
    ```

---

## 4. Interface Graphique (GUI) & Saisie de Tour

C'est ici que l'inspiration du mode Companion est la plus forte. Nous allons utiliser le sélecteur de
personnage existant (`self._player_selector`) pour orchestrer la saisie.

- **Fichier cible : `tabletop_view.py`**
  - Variables d'état de tour :
    - `self._pending_intents: dict[str, str] = {}` (stocke les intentions validées par les joueurs
      pour le tour en cours).
    - `self._active_players: list[str] = []` (liste des entités de type `player` chargées).
  - Comportement de saisie (`_on_send_message`) :
    - Si `self._mode == "Multiplayer"` :
      1. Récupérer le joueur actif actuellement sélectionné dans `self._player_selector`.
      2. Enregistrer sa saisie dans `self._pending_intents[player_id] = text`.
      3. Afficher un retour visuel direct dans le chat, par exemple : `[Aria la Rouge prépare : "Je
         charge le garde."]`.
      4. Vider le champ de saisie texte.
      5. Déterminer quels joueurs de `self._active_players` n'ont pas encore soumis d'intention.
      6. S'il en reste :
         - Sélectionner automatiquement le joueur suivant dans `self._player_selector` pour inviter
           à la saisie.
         - Laisser la zone de saisie active (ne pas bloquer l'UI).
      7. Si tous les joueurs ont validé leur intention :
         - Bloquer l'UI.
         - Instancier le `NarrativeWorker` en lui passant le dictionnaire complet `self._pending_intents`.
         - Lancer la résolution simultanée.
         - Une fois la résolution terminée (`_on_turn_complete`), vider `self._pending_intents` et
           incrémenter `self._turn_id`.

---

## 5. Création de Save & Gestion des Personnages

- **Fichier cible : `setup_view.py`**
  - Ajouter l'option de difficulté `"Multiplayer"` (traduite) dans le combobox de création de partie.
- Création de personnages :
  - Pour lancer une partie multijoueur, l'utilisateur a besoin de plusieurs personnages. Nous allons
    capitaliser sur le Creator Studio existant (onglet Entities / Entités), qui permet déjà de créer des
    entités de type `player` à la volée avec leurs noms, descriptions et statistiques.
  - Ainsi, pour jouer en multijoueur : l'utilisateur crée une partie en mode `"Multiplayer"`, ouvre le
    Creator Studio pour y ajouter ses personnages joueurs, puis joue son premier tour.

---

### Prochaines étapes suggérées

Une fois ce plan validé, je vais :

1. ~~Créer le dossier `maintenance/features/feature-multiplayer/`~~ → **dossier `maintenance/Multiplayer/`**
   (déjà créé) avec `TODO.md` et `CHANGELOG.md` (le `DOC.md` restera léger).
2. ~~Déclarer dans `collab/gemini/EN_COURS.md`~~ → **`collab/claude/EN_COURS.md`** (l'implémenteur est Claude).
3. Implémenter et tester la feature pas à pas (voir l'ordre dans `TODO.md`).
</content>
</invoke>
