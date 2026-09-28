# DOC — Phase 4 : Outillage de création & Créateur de mods par LLM

## 1. Vue d'Ensemble & Objectifs Architecturaux

La Phase 4 dote le moteur Axiom AI d'un ensemble complet d'outils destinés à la fois aux moddeurs humains et aux agents d'intelligence artificielle :

1. **Échafaudage Rapide (`axiom mod new`)** :
   Permet d'initialiser en une commande un mod prêt à l'emploi selon l'archétype souhaité (`hook`, `slot`, `data`), avec des modèles de tests et de localisation.
2. **Harnais de Validation Déterministe (`axiom mod test`)** :
   Offre une vérification statique et dynamique sans faille :
   - Conformité formelle du manifeste (`mod.toml`).
   - Vérification de la syntaxe des hooks et slots.
   - Respect strict de la **Règle D4** : aucun import de package UI (`PyQt6`, `ui`, `main_web`) n'est autorisé dans la logique du mod sauf déclaration explicite d'une dépendance UI.
   - Initialisation et dépilement de cycle de vie en contexte isolé.
   - Exécution bornée de la suite de tests unitaires via `pytest`.
3. **Mode Développement avec Hot-Reload (`axiom mod dev`)** :
   Surveille les fichiers sources du mod et déclenche un rechargement à chaud à chaque enregistrement. Grâce à la **Règle D11**, l'appel systématique à `ctx.cleanup()` retire tous les hooks, contributions de slots et trampolines de patches avant d'instancier un nouveau contexte propre.
4. **Créateur de Mods par LLM Headless (`axiom mod generate` & API Web)** :
   Met en œuvre la deuxième promesse du système (§1.2) : la création de mod entièrement automatisable par un modèle de langage.
   Conformément aux règles de sûreté (§12 & D14) :
   - Tout mod généré est d'abord instancié dans un bac à sable temporaire de staging (`~/.cache/AxiomAI/staged_mods/<mod_id>/`).
   - Un diff textuel unifié est calculé pour chaque fichier.
   - Les tests automatisés (`test_mod`) sont exécutés dans la sandbox.
   - **Garde-fou absolu** : Aucun fichier n'est écrit dans le répertoire de jeu `mods/` et aucun mod n'est activé tant que l'utilisateur n'a pas explicitement validé le diff (en CLI ou via l'API Web).

---

## 2. Architecture Technique des Nouveaux Modules

```
axiom/
├── kernel/
│   ├── scaffold.py     # Fabrique de squelette de mod (hook/slot/data)
│   ├── tester.py       # Validateur structurel, filtre D4 UI & runner pytest
│   ├── dev.py          # Watcher mtime et hot-reload de mod (D11)
│   └── llm_creator.py  # Orchestrateur de génération LLM, staging & diffs
└── cli/
    └── mods_cmd.py     # Sous-commandes: new, test, dev, generate, validate, patches, pack...
```

---

## 3. Guide des Commandes CLI

### A. Échafauder un nouveau mod
```bash
# Mod basé sur les événements (hook)
axiom mod new community.weather --type hook

# Mod fournissant des slots
axiom mod new community.reputation --type slot

# Mod avec stockage persistant
axiom mod new community.quest_log --type data --dir my_mods/quest_log
```

### B. Tester un mod ou une archive `.axmod`
```bash
axiom mod test mods/community.weather
axiom mod test dist/mods/community.weather-0.1.0.axmod
```

### C. Développer en direct avec rechargement automatique
```bash
axiom mod dev mods/community.weather
```

### D. Générer un mod via IA avec inspection préalable du diff
```bash
axiom mod generate "Ajoute une jauge d'endurance qui diminue lors des déplacements"
```
Affiche le diff complet dans le terminal :
```diff
+++ b/mod.toml
@@ -0,0 +1,11 @@
+[mod]
+id = "community.stamina"
+version = "0.1.0"
...
```
Demande confirmation interactive avant toute modification du dossier `mods/` :
```text
Confirmer l'installation et l'activation de ce mod ? [y/N]:
```

---

## 4. Endpoints API Web (`main_web.py`)

- `GET /api/mods` : Liste les mods installés (id, version, statut d'activation, chemin, version d'API).
- `POST /api/mods/generate` :
  - **Requête** : `{"prompt": "Créer un système de météo dynamique"}`
  - **Réponse** : JSON contenant `mod_id`, `staged_dir`, `file_diffs`, `tests_passed`, `error_report`, et `manifest`.
- `POST /api/mods/apply` :
  - **Requête** : `{"staged_dir": "/home/user/.cache/AxiomAI/staged_mods/community.weather"}`
  - **Réponse** : `{"status": "success", "installed_path": "...", "axmod_path": "..."}`
