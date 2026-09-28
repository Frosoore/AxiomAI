# Le système de mods (`.axmod`)

*[Read this guide in English](mods.md)*

Axiom AI adopte une architecture de **micro-noyau modulaire** (`axiomai-engine 1.0.0`) : le moteur de base n'embarque aucune logique métier JDR en dur, et tout le gameplay, la narration, la mémoire, les fournisseurs d'IA et les interfaces sont portés par des **mods** au format `.axmod`.

Ce guide détaille la vision architecturale, la cartographie du système, la liste des 12 mods officiels, le guide d'écriture pour les moddeurs, et les garanties de robustesse.

---

## 1. Vision et Promesses Fondamentales

Le système de mods repose sur trois promesses fondatrices (§1.2) :

1. **Versatilité sans obésité :** Le noyau (`axiom/`) ne contient aucune règle métier propre au JDR, aucun prompt en dur, ni aucune dépendance lourde vers des bibliothèques externes non déclarées.
2. **Plug and play, y compris pour un LLM :** L'échafaudage (`scaffold`), le banc d'essai (`tester`), le rechargement à chaud (`dev`) et le créateur LLM (`llm_creator`) permettent de concevoir des extensions testées et vérifiées en bac à sable avec un diff textuel explicite.
3. **Réversibilité et facilité :** Tout enregistrement passe par `ModContext` ; désactiver un mod restaure l'état antérieur sans résidu de mémoire ni corruption de base de données.

---

## 2. Cartographie du Système Modulaire

```
                     ┌──────────────────────────────────────────────┐
                     │          Store Distant / Index JSON           │
                     │         (axiom mods search / install)        │
                     └──────────────────────┬───────────────────────┘
                                            │ Hash SHA-256
                                            ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             ÉCOSYSTÈME DE MODS (.axmod)                          │
├──────────────────────┬─────────────────────────────┬─────────────────────────────┤
│   MODÈLE DE MONDE    │     PIPELINE DE TOUR        │          MÉMOIRE            │
│     axiom.world      │        axiom.turn           │    axiom.rag (ChromaDB)     │
│   (Stats, Entités)   │   (Fabric API du moteur)    │ axiom.living_memory (Faits) │
├──────────────────────┼─────────────────────────────┼─────────────────────────────┤
│  MÉCANIQUES DE JEU   │     FOURNISSEURS & ART      │         INTERFACES          │
│      axiom.time      │       axiom.providers       │        axiom.ui.web         │
│   axiom.inventory    │     axiom.illustrations     │        axiom.ui.qt          │
│  core.stat_dynamics  │    (Gemini, Ollama, SD)     │         axiom.cli           │
└───────────┬──────────┴──────────────┬──────────────┴──────────────┬──────────────┘
            │ Hooks                   │ Slots (Collect, Chain, Excl)│ Patches (@patchable)
            ▼                         ▼                             ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                            MICRO-NOYAU (axiomai-engine 1.0.0)                     │
├──────────────────────────────────────────────────────────────────────────────────┤
│ • Chargeur & Résolveur DAG (Topologie, Conflits, Ordre utilisateur)              │
│ • Registre Central (Hooks, Slots typés, Services inter-mods)                     │
│ • Bus d'Exécution & Gel de Pas (step_patch_freeze, KernelStepContext)            │
│ • Persistance Transactionnelle (TurnWriteBatch, Époques de Session)              │
│ • Registre de Sauvegarde Déclaratif (EVENTS, STEP_KEYED, VERSIONED_KV, CUSTOM)   │
│ • CLI & Mode Sans Échec (--safe-mode natif sans UI)                              │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Répertoire des 12 Mods Officiels Extraits

| Mod ID | Rôle & Responsabilité | Points d'ancrage clés | Politique de Persistance |
| --- | --- | --- | --- |
| **`axiom.world`** | Entités, statistiques de base, règles RulesEngine et graphe de lieux. | Hooks `gather_context`, `arbitrate_mutations` ; Slot `entity_types`. | `versioned_kv` |
| **`axiom.turn`** | Pipeline narratif, boucle de correction, routage des tool-calls. | Hook `execute_step` ; Slots `prompt_sections`, `output_fields`, `stream_filter`, `final_text_filter`, `llm_backend`. | `events` (`Event_Log`) |
| **`core.stat_dynamics`** | Évolution temporelle passive, repos, fatigue et décroissance des jauges. | Hook `arbitrate_stats`, `after_step`. | `step_keyed_table` (`Modifier_Snapshots`) |
| **`axiom.time`** | Horloge diégétique, Timekeeper, Timeline et Chronicler hors-champ. | Hook `after_step` ; Service `time` ; Slot `output_fields` (`time_elapsed_minutes`). | `step_keyed_table` (`Timeline`, `Scheduled_Events`) |
| **`axiom.inventory`** | Arborescence d'objets et conteneurs imbriqués (profondeur max 5). | Service `inventory` ; Slot `output_fields` (`inventory_changes`). | `step_keyed_table` (`Inventory_Snapshots`) |
| **`axiom.rag`** | Mémoire vectorielle locale via ChromaDB et Sentence-Transformers. | Hook `after_step` ; Slot `prompt_sections` ; Service `rag`. | `custom` (rollback vectoriel chirurgical) |
| **`axiom.living_memory`** | Distillation symbolique de faits, croyances et modèles mentaux d'entités. | Hook `after_step` (garde d'époque) ; Service `living_memory`. | `step_keyed_table` (`Facts`, `Observations`, `Mental_Models`) |
| **`axiom.providers`** | Pilotes d'inférence (Gemini, Ollama, OpenAI-compatible) et tests de connexion. | Slot `axiom.turn:llm_backend` ; Slot ouvert `axiom.providers:drivers`. | Aucune (stateless) |
| **`axiom.illustrations`** | Génération visuelle par tour (Stable Diffusion / ComfyUI). | Hook `after_step` (post-commit callback) ; Service `illustrations`. | `custom` (nettoyage des PNG au rewind) |
| **`axiom.ui.web`** | Serveur HTTP local et SPA Web Tabletop / Studio. | Service `web_ui` ; Slots ouverts `side_panel`, `settings_tab`, `action_button`. | Aucune |
| **`axiom.ui.qt`** | Interface graphique desktop native PySide6. | Service `qt_ui` ; Slots ouverts `sidebar_widget`, `settings_tab`. | Aucune |
| **`axiom.cli`** | Aventure textuelle interactive dans le terminal (`axiom play`). | Service `cli_play`. | Aucune |

---

## 4. Guide de Référence pour l'Auteur de Mod

Pour concevoir un mod, l'auteur dispose de trois méthodes complémentaires :

### A. Génération assistée par LLM
```bash
axiom mod generate "Ajoute une mécanique de soif qui augmente lors des déplacements dans le désert"
```
Le moteur prépare le mod en sandbox (`~/.cache/AxiomAI/staged_mods/`), valide le manifeste, exécute le banc de tests unitaires et affiche le diff coloré avant de solliciter la confirmation de l'utilisateur.

### B. Échafaudage manuel & développement en direct
```bash
# 1. Créer le squelette de projet
axiom mod new monauteur.mafeature --type slot

# 2. Lancer la boucle de développement à chaud
axiom mod dev mods/monauteur.mafeature/

# 3. Tester et empaqueter en archive .axmod
axiom mod test mods/monauteur.mafeature/
axiom mod pack mods/monauteur.mafeature/
```

### C. Modèle canonique d'un fichier `main.py`
```python
from axiom.kernel.context import ModContext

def init(ctx: ModContext) -> None:
    # 1. Contribuer au prompt du tour
    def inject_prompt(step_ctx):
        return ("system", 50, "Règle spéciale : Le joueur a soif.")
    ctx.contribute_slot("axiom.turn:prompt_sections", inject_prompt)

    # 2. Intercepter les sorties LLM
    def handle_output(data, turn_ctx):
        # Application atomique dans le TurnWriteBatch
        turn_ctx.write_batch.stage_event("soif_update", {"valeur": 10})
    ctx.contribute_slot("axiom.turn:output_fields", {"soif_level": handle_output})

    # 3. Patch chirurgical réversible si nécessaire (D11)
    def patch_calcul(orig_fn, *args, **kwargs):
        res = orig_fn(*args, **kwargs)
        return res * 1.5
    ctx.patch("axiom.world:calculate_stamina", "around", patch_calcul)
```

---

## 5. Gestion des Dépendances et Licence

- **Dépendances Python (`[python].requires`) :** Les mods peuvent déclarer des packages Python requis dans leur `mod.toml`. Le chargeur vérifie statiquement ces dépendances au démarrage et désactive gracieusement le mod avec un avertissement si des packages sont absents (Règle D-7), sans aucun installateur lourd.
- **Licence des mods tiers (AGPLv3 §7(b)) :** Les mods tiers interagissant uniquement via l'API publique (`ModContext`, hooks, slots, tables déclaratives) constituent des œuvres indépendantes libres de choisir leur licence (MIT, Apache 2.0, propriétaire, etc.). Les patches intrusifs en mémoire restent soumis aux obligations de réciprocité de l'AGPLv3. Voir `docs/licensing_mods.md`.

---

## 6. Commandes CLI pour le Store et la Gestion des Mods

```bash
# Lister les mods installés
axiom mods list

# Activer ou désactiver un mod
axiom mods enable community.lockpicking
axiom mods disable community.lockpicking

# Rechercher sur le Store distant
axiom mods search "lockpicking"
axiom mods search "" --tag official

# Installer un mod depuis le Store avec vérification de hash SHA-256
axiom mods install community.lockpicking

# Mettre à jour les mods installés
axiom mods update

# Lancer le moteur en mode sans échec (neutralise les mods tiers)
axiom play MyWorld.db --safe-mode
```

---

## 7. Bilan de Conformité et de Robustesse

* **Tests de non-régression :** **96 tests d'intégration unitaires et transversaux** sont au vert (100 %) sans aucun avertissement bloquant.
* **Harnais Golden Step :** Les opérations critiques de cycle de vie (10 tours consécutifs, Rembobinage à $T-2$, Fork de chronologie, Export et Réimportation bit-à-bit d'archive `.axiomsave`) s'exécutent avec un **diff strictement nul**.
* **Contrat Headless PyPI :** `export_engine.py` garantit que le paquet `axiomai-engine 1.0.0` ne comporte aucune fuite vers `ui/`, `workers/`, `web/` ou `mods/`.
* **Statut de sécurité :** Le démarrage d'urgence avec le drapeau `--safe-mode` est opérationnel sur toutes les interfaces.
