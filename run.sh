#!/usr/bin/env bash
# ============================================================
# Axiom AI — Linux / macOS launch script
# Usage: bash run.sh
#        chmod +x run.sh && ./run.sh
# Works on both Ubuntu/Linux and macOS (both POSIX/bash).
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Portability helpers (Linux vs macOS) ─────────────────────
OS="$(uname -s)"   # "Linux" or "Darwin" (macOS)

# macOS ships `shasum -a 256` instead of GNU `sha256sum`.
hash_file() {
    if command -v sha256sum &>/dev/null; then
        sha256sum "$1" | cut -d' ' -f1
    else
        shasum -a 256 "$1" | cut -d' ' -f1
    fi
}

# ── Prerequisites check ──────────────────────────────────────
echo "--- Axiom AI System Check ---"

if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found."
    echo "Please install Python 3.11+ and venv:"
    if [ "$OS" = "Darwin" ]; then
        echo "  macOS: brew install python@3.12   (or download from python.org)"
    else
        echo "  sudo apt update && sudo apt install python3 python3-pip python3-venv"
    fi
    exit 1
fi

# Check for venv module specifically (common pitfall on Ubuntu; bundled on macOS).
if ! python3 -m venv --help &>/dev/null; then
    echo "ERROR: the python3 venv module is missing."
    if [ "$OS" = "Darwin" ]; then
        echo "  macOS: reinstall Python from python.org or 'brew install python@3.12'."
    else
        echo "  sudo apt update && sudo apt install python3-venv"
    fi
    exit 1
fi

# Check for common Qt/PySide6 system dependencies on Linux only.
# libxcb-cursor0 and libqt6svg6 are frequent missing libraries for PySide6 on Ubuntu.
# (macOS PySide6 wheels are self-contained, so this block is skipped there.)
if [ "$OS" = "Linux" ] && command -v ldconfig &>/dev/null; then
    if ! ldconfig -p | grep -q "libxcb-cursor.so.0"; then
        echo "Warning: libxcb-cursor0 might be missing (required for PySide6 GUI)."
        echo "You can install it with:"
        echo "  Ubuntu/Debian/Mint: sudo apt update && sudo apt install libxcb-cursor0"
        echo "  Fedora/RHEL:        sudo dnf install xcb-cursor"
        echo "  Arch/Manjaro:       sudo pacman -S xcb-cursor"
    fi
    if ! ldconfig -p | grep -q "libQt6Svg.so.6"; then
        echo "Warning: libqt6svg6 might be missing (required for SVG icons)."
        echo "You can install it with:"
        echo "  Ubuntu/Debian/Mint: sudo apt update && sudo apt install libqt6svg6"
        echo "  Fedora/RHEL:        sudo dnf install qt6-svg"
        echo "  Arch/Manjaro:       sudo pacman -S qt6-svg"
    fi
fi

PYTHON_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
PYTHON_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
PYTHON_VER="${PYTHON_MAJOR}.${PYTHON_MINOR}"

if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]; }; then
    echo "ERROR: Python 3.11+ required (found $PYTHON_VER)."
    exit 1
fi

echo "Using Python $PYTHON_VER"

# ── Virtual environment ──────────────────────────────────────
VENV_DIR=".venv"

# Check if venv exists and is valid for the current location
RECREATE_VENV=false
if [ ! -f "$VENV_DIR/bin/activate" ] || [ ! -f "$VENV_DIR/bin/python3" ]; then
    RECREATE_VENV=true
else
    # Detect if the venv was moved (hardcoded absolute paths in activate script)
    # We source it in a subshell to see what VIRTUAL_ENV it actually sets
    VENV_ACTIVATE_PATH=$(bash -c "source \"$VENV_DIR/bin/activate\" 2>/dev/null && echo \$VIRTUAL_ENV" || echo "broken")
    if [ "$VENV_ACTIVATE_PATH" != "$SCRIPT_DIR/$VENV_DIR" ]; then
        echo "Virtual environment appears invalid or moved (pointing to '$VENV_ACTIVATE_PATH'). Recreating..."
        RECREATE_VENV=true
    fi
fi

if [ "$RECREATE_VENV" = true ]; then
    echo "Creating/Repairing virtual environment in $VENV_DIR..."
    rm -rf "$VENV_DIR"
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

# ── Dependency Installation ──────────────────────────────────
REQ_HASH=$(hash_file requirements.txt)
MARKER="$VENV_DIR/.deps_hash"

if [ ! -f "$MARKER" ] || [ "$(cat "$MARKER")" != "$REQ_HASH" ]; then
    echo "Installing/updating dependencies..."
    python3 -m pip install --upgrade pip
    python3 -m pip install -r requirements.txt
    echo "$REQ_HASH" > "$MARKER"
else
    echo "Dependencies up to date (skip)."
fi

# ── Startup Validation ───────────────────────────────────────
# Run a quick headless check of the environment before launching the GUI
echo "Running environment validation..."
python3 debug/startup_check.py

# ── Launch ───────────────────────────────────────────────────
echo "Starting Axiom AI..."
# Use exec to replace the shell process with the python process
exec python3 main.py "$@"
