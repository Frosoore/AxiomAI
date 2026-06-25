# macOS compatibility — run from source

Objectif (demandé par l'utilisateur) : pouvoir lancer Axiom sur macOS via un
script `run.sh` (comme Linux/Windows), **sans** app double-cliquable / .dmg /
notarisation. Et que l'app tourne réellement.

## Audit (fait)
- [x] Toolkit GUI = PySide6 → natif macOS (arm64 + x86_64), rien à changer.
- [x] Dépendances (chromadb, sentence-transformers/torch, httpx, google-genai,
      Pillow, rank-bm25, tomlkit) → toutes avec wheels macOS.
- [x] Branches plateforme : seules des branches `sys.platform == "win32"`
      (VC++ redist, WinError/verrous fichiers) → **no-op sur macOS**. Aucune
      branche `== "linux"` qui exclurait darwin.
- [x] `axiom/paths.py` : déjà un fallback POSIX `~/.config` / `~/.cache` /
      `~/AxiomAI` qui couvre macOS.
- [x] Ouverture externe : un seul appel, `QDesktopServices.openUrl` (Qt,
      multiplateforme), et derrière le garde win32. Aucun `xdg-open` en dur.
- [x] Aucun chemin Linux codé en dur (`/usr`, `/home`, `/tmp`).

## À faire
- [x] `run.sh` portable Linux + macOS (le vrai point de blocage) :
      - `sha256sum` absent sur macOS → helper `hash_file` (sha256sum sinon
        `shasum -a 256`).
      - message « python3 manquant » adapté par OS (brew vs apt).
      - bloc de check Qt `ldconfig` réservé à Linux (déjà ignoré sur macOS mais
        explicité).
- [x] README : indiquer que macOS utilise le même `bash run.sh`.

## Reste (hors périmètre / honnêteté)
- [ ] **Passe de QA sur un VRAI Mac** : comme pour Windows (l'audit statique
      « moteur Windows-safe » s'était révélé faux), tant que ce n'est pas lancé
      sur une vraie machine, on dit « ça devrait marcher », pas « ça marche ».
      Points à confirmer : torch sur Apple Silicon (arm64), 1er téléchargement
      du modèle d'embedding, rendu Qt.
- [ ] App `.app`/`.dmg` signée+notarisée → NON demandé, non fait.
