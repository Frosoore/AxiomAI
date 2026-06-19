#!/usr/bin/env bash
# ============================================================
# Axiom AI — publie le moteur `axiomai-engine` en NOUVELLE version sur PyPI.
#
# Enchaîne : bump de version -> export PyPI-ready -> build (sdist+wheel)
#            -> twine check -> twine upload.
#
# Usage :
#   ./publish_engine.sh patch          # 0.1.6 -> 0.1.7 puis publie sur PyPI
#   ./publish_engine.sh minor          # 0.1.6 -> 0.2.0
#   ./publish_engine.sh major          # 0.1.6 -> 1.0.0
#   ./publish_engine.sh --set 1.2.3    # fixe la version exacte
#   ./publish_engine.sh patch --test   # publie sur TestPyPI (répétition sans risque)
#   ./publish_engine.sh patch --dry    # build + check SEULEMENT, n'upload PAS
#
# Le TOKEN PyPI n'est JAMAIS stocké ici : twine le demande au moment de l'upload.
#   - À l'invite "username" : tape  __token__
#   - À l'invite "password" : colle ton token  pypi-...
#   (ou exporte-les avant : export TWINE_USERNAME=__token__ TWINE_PASSWORD=pypi-...)
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PY=".venv/bin/python"
EXPORT_DIR="dist/axiomai-engine"

# ── 0. Garde-fous d'environnement ───────────────────────────
if [ ! -x "$PY" ]; then
    echo "ERREUR : $PY introuvable. Lance d'abord ./run.sh pour créer le venv." >&2
    exit 1
fi
if ! "$PY" -c "import build" 2>/dev/null; then
    echo "ERREUR : module 'build' manquant. Installe-le :  $PY -m pip install build" >&2
    exit 1
fi
if ! "$PY" -c "import twine" 2>/dev/null; then
    echo "ERREUR : module 'twine' manquant. Installe-le :  $PY -m pip install twine" >&2
    exit 1
fi

# ── 1. Parse des arguments ──────────────────────────────────
VERSION_ARG=()
REPO_FLAG=()         # --repository testpypi le cas échéant
DRY=false
TARGET="PyPI"

usage() { sed -n '2,28p' "$0"; exit 1; }

[ $# -ge 1 ] || usage
while [ $# -gt 0 ]; do
    case "$1" in
        patch|minor|major) VERSION_ARG=(--bump "$1") ;;
        --set)             shift; VERSION_ARG=(--set-version "$1") ;;
        --test)            REPO_FLAG=(--repository testpypi); TARGET="TestPyPI" ;;
        --dry)             DRY=true ;;
        -h|--help)         usage ;;
        *) echo "Argument inconnu : $1" >&2; usage ;;
    esac
    shift
done
[ ${#VERSION_ARG[@]} -gt 0 ] || { echo "ERREUR : précise patch|minor|major ou --set X.Y.Z" >&2; usage; }

# ── 2. Export + bump + build (export_engine.py fait le gros) ─
echo "=== Export + bump + build du moteur ==="
"$PY" export_engine.py "${VERSION_ARG[@]}" --build --force

NEW_VERSION="$("$PY" -c 'import axiom; print(axiom.__version__)')"
echo "Version du paquet : $NEW_VERSION"

# ── 3. Vérification des artefacts ───────────────────────────
echo "=== twine check ==="
"$PY" -m twine check "$EXPORT_DIR"/dist/*

# ── 4. Upload (sauf --dry) ──────────────────────────────────
if [ "$DRY" = true ]; then
    echo
    echo "[--dry] Build vérifié, AUCUN upload. Artefacts dans : $EXPORT_DIR/dist/"
    echo "Pour publier : ./publish_engine.sh (sans --dry)"
    exit 0
fi

echo
echo ">>> Prêt à publier axiomai-engine $NEW_VERSION sur $TARGET."
read -r -p ">>> Confirmer l'upload ? [oui/N] " ANSWER
case "$ANSWER" in
    oui|o|y|yes|O|Y) ;;
    *) echo "Annulé. (Artefacts toujours dans $EXPORT_DIR/dist/)"; exit 0 ;;
esac

echo "=== twine upload → $TARGET ==="
echo "(username = __token__  ;  password = ton token pypi-...)"
"$PY" -m twine upload "${REPO_FLAG[@]}" "$EXPORT_DIR"/dist/*

echo
echo "✅ Publié : axiomai-engine $NEW_VERSION sur $TARGET"
echo "Pense à committer le bump de version (axiom/__init__.py) et, si tu veux, à taguer :"
echo "    git add axiom/__init__.py && git commit -m \"release: axiomai-engine $NEW_VERSION\""
echo "    git tag v$NEW_VERSION"
