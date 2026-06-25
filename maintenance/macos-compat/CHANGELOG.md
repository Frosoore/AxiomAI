# CHANGELOG — macOS compatibility (run from source)

## 2026-06-25 — Launcher portable Linux + macOS

### Constat (audit)
Le code est déjà essentiellement compatible macOS : GUI en PySide6 (natif Mac),
toutes les dépendances ont des wheels macOS, et les seules branches plateforme
sont des gardes `sys.platform == "win32"` (VC++ redistributable, verrous de
fichiers Windows) qui deviennent des no-op sur macOS. `axiom/paths.py` a déjà un
fallback POSIX (`~/.config`, `~/.cache`, `~/AxiomAI`) couvrant macOS, et la seule
ouverture externe passe par `QDesktopServices.openUrl` (Qt, multiplateforme).
→ Seul le launcher `run.sh` était réellement bloquant.

### Modifié
- `run.sh` rendu portable Linux + macOS (un seul script, les deux sont bash) :
  - en-tête « Linux / macOS » ; détection `OS="$(uname -s)"`.
  - **helper `hash_file`** : macOS n'a pas `sha256sum` (GNU) mais `shasum -a 256`.
    Le calcul d'empreinte de `requirements.txt` (marqueur de réinstall des deps)
    utilise désormais `sha256sum` si présent, sinon `shasum -a 256`. C'était LE
    point qui aurait fait échouer `run.sh` sur Mac.
  - messages « python3 / venv manquant » adaptés par OS (brew/python.org vs apt).
  - bloc de vérification des libs Qt (`ldconfig`, `libxcb-cursor`, `libQt6Svg`)
    explicitement réservé à Linux (les wheels PySide6 macOS sont autonomes).
- `README.md` : section Quick Start → « Linux / macOS : bash run.sh ».

### Vérifié
- `bash -n run.sh` : syntaxe OK.
- `hash_file` testé : les deux branches (`sha256sum` et `shasum -a 256`)
  produisent la même empreinte → la logique de marqueur de deps reste correcte.

### NON fait (et pourquoi)
- **Test sur un vrai Mac** : impossible depuis cette machine (Linux). Comme la
  leçon Windows l'a montré (l'audit statique « Windows-safe » était faux), tant
  qu'on n'a pas lancé sur une vraie machine Apple, c'est « ça devrait marcher »,
  pas « validé ». À confirmer en QA Mac : torch sur Apple Silicon (arm64),
  premier téléchargement du modèle d'embedding, rendu Qt.
- App `.app`/`.dmg` signée/notarisée : non demandé.
