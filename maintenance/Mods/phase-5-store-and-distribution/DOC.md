# DOC — Phase 5 : Store, Dépendances, Licence & Distribution

## 1. Vue d'Ensemble & Objectifs Architecturaux

La Phase 5 parachève la vision d'un écosystème modulaire ouvert pour Axiom AI en concrétisant les trois promesses fondatrices (§1.1, §1.2, §14 de `DOC.md`) et les arbitrages D-7, D-8 et D-9 :

1. **Le Protocole du Store Distant (Index, Recherche & Installation Sécurisée)** :
   - Mise en place d'un registre décentralisé ou distant de paquets `.axmod` (`axiom/kernel/store.py`).
   - Recherche textuelle plein-texte filtrable par tags, compatibilité d'API et identifiants.
   - Vérification cryptographique systématique des condensats SHA-256 (§6.12) : tout téléchargement corrompu ou altéré déclenche une `ModIntegrityError` et annule l'installation.
   - Catalogue initial généré sous `dist/mods/store_index.json` pour l'ensemble des mods officiels et de démonstration.

2. **Le Contrat de Dépendances Python Légères (D-7)** :
   - Manifeste `mod.toml` étendu avec la table déclarative `[python].requires = [...]`.
   - Vérification statique non-bloquante au chargement (`axiom/kernel/dependencies.py`) via `importlib.metadata.version` et compatibilité `packaging.specifiers.SpecifierSet`.
   - Aucun installateur `pip` lourd n'est exécuté en tâche de fond. Si une dépendance Python système ou pip manque à l'appel, le chargeur journalise un avertissement clair et désactive le mod en toute sécurité sans faire crasher le moteur.

3. **Frontière Juridique et Licence des Mods (D-9, §14)** :
   - Rédaction de `docs/licensing_mods.md` et mise à jour de la mention `NOTICE`.
   - Formalisation explicite de la frontière entre le moteur sous licence AGPLv3 et les mods tiers indépendants.
   - Les mods qui interagissent uniquement via l'API publique (`ModContext`, hooks, slots, services, format `.axmod`) constituent des œuvres dérivées indépendantes et peuvent choisir leur propre licence (MIT, Apache 2.0, propriétaire, etc.) au titre de l'exception §7(b) de l'AGPLv3.
   - À l'inverse, les patches intrusifs en mémoire (monkeypatching) modifiant les entrailles privées du noyau restent soumis aux obligations de partage de code source de l'AGPLv3.

4. **Assainissement du Package PyPI Headless (`axiomai-engine`) (D-8)** :
   - Le script de packaging `export_engine.py` isole strictement le micro-noyau headless (`axiom/`).
   - Exclusion formelle de tout mod (`mods/`), de toute interface graphique ou web (`ui/`, `web/`, `main_web.py`), des workers applicatifs et des univers de jeu.
   - Validation automatisée de l'étanchéité headless (`check_headless`).
   - Incrément de version formel à `1.0.0` dans `axiom/__init__.py`.

5. **Expérience Utilisateur Unifiée (CLI & Web API)** :
   - Commandes CLI : `axiom mods search`, `axiom mods install`, `axiom mods update`.
   - Endpoints Web API : `GET /api/store/search`, `POST /api/store/install`.

---

## 2. Architecture Technique des Nouveaux Modules

```
axiom/
├── kernel/
│   ├── dependencies.py     # Vérification des dépendances Python [python].requires (D-7)
│   ├── store.py            # Client du Store distant, vérification SHA-256 & installation
│   └── manifest.py         # Support étendu de ModManifest.python_requires
├── cli/
│   └── mods_cmd.py         # Commandes search, install, update
docs/
└── licensing_mods.md       # Spécification juridique de la frontière AGPLv3 / Mods tiers
dist/
└── mods/
    └── store_index.json    # Catalogue officiel d'index du Store
```

---

## 3. Spécification Détaillée

### A. Déclaration des Dépendances Python (`mod.toml`)
```toml
[mod]
id = "community.analytics"
version = "1.0.0"
axiom_api = 1
name = "Mod d'Analytique Avancée"
description = "Calcule des métriques statistiques en fin de tour."

[python]
requires = [
    "numpy>=1.20.0",
    "scipy"
]
```

### B. Contrôle d'Intégrité SHA-256
Chaque entrée dans le catalogue du Store présente la forme :
```json
{
  "id": "axiom.turn",
  "version": "1.0.0",
  "axiom_api": 1,
  "name": "Moteur de Tour de Rôle JDR",
  "description": "...",
  "download_url": "https://store.axiomai.dev/mods/axiom.turn.axmod",
  "sha256": "81f1ffb91d297a7a5c8df5650201e792ba26efc689366432b03fa5789f2cfc3e",
  "python_requires": [],
  "dependencies": ["axiom.world"],
  "tags": ["core", "official", "turn"]
}
```
Lors de l'appel à `install_mod_from_store`, le fichier téléchargé fait l'objet d'un calcul de hash SHA-256 en continu :
- Si le hash ne correspond pas au hash catalogué, une exception `ModIntegrityError` est levée immédiatement et le fichier temporaire est détruit.
- Si le hash est vérifié, l'archive est validée et extraite dans `mods/<mod_id>`.

---

## 4. Guide des Commandes CLI

### A. Rechercher sur le Store
```bash
axiom mods search "inventory"
axiom mods search "" --tag official
```

### B. Installer un mod depuis le Store
```bash
axiom mods install community.lockpicking --index dist/mods/store_index.json
```

### C. Mettre à jour les mods installés
```bash
axiom mods update --index dist/mods/store_index.json
```

---

## 5. Endpoints API Web (`main_web.py`)

- `GET /api/store/search?q=<query>&tag=<tag>` : Interroge l'index distant et retourne la liste des mods disponibles.
- `POST /api/store/install` :
  - **Requête** : `{"mod_id": "community.lockpicking", "index_url": "..."}`
  - **Réponse** : `{"status": "success", "installed_path": "mods/community.lockpicking", "manifest": {...}}`
