#!/usr/bin/env bash
# ============================================================
# Axiom AI — Test Runner (Zero-config fallback)
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🧪 Axiom AI Test Suite Runner"
echo "--------------------------"

# ── Virtual environment ──────────────────────────────────────
VENV_DIR=".venv"

# Check if venv exists and is valid for the current location
RECREATE_VENV=false
if [ ! -f "$VENV_DIR/bin/activate" ] || [ ! -f "$VENV_DIR/bin/python3" ]; then
    RECREATE_VENV=true
else
    # Detect if the venv was moved (hardcoded absolute paths in activate script)
    VENV_ACTIVATE_PATH=$(bash -c "source \"$VENV_DIR/bin/activate\" 2>/dev/null && echo \$VIRTUAL_ENV" || echo "broken")
    if [ "$VENV_ACTIVATE_PATH" != "$SCRIPT_DIR/$VENV_DIR" ]; then
        echo "Virtual environment appears invalid or moved (pointing to '$VENV_ACTIVATE_PATH'). Recreating..."
        RECREATE_VENV=true
    fi
fi

if [ "$RECREATE_VENV" = true ]; then
    echo "Creating/Repairing virtual environment in $VENV_DIR..."
    rm -rf "$VENV_DIR"
    if ! python3 -m venv "$VENV_DIR" 2>/dev/null; then
        echo "ERROR: Could not create virtual environment. Ensure python3-venv is installed."
        exit 1
    fi
fi

source "$VENV_DIR/bin/activate"

# Install requirements
echo "Verifying dependencies..."
python3 -m pip install -q --upgrade pip
python3 -m pip install -q -r requirements.txt -r requirements-dev.txt

# Determine if we can run GUI tests (Qt)
PYTEST_CMD="python3 -m pytest"
if command -v xvfb-run &>/dev/null; then
    RUNNER="xvfb-run $PYTEST_CMD"
else
    RUNNER="$PYTEST_CMD"
fi

# With arguments: pass them to pytest as-is (e.g., ./test.sh tests/test_llm_base.py).
if [ "$#" -gt 0 ]; then
    echo "Running tests..."
    $RUNNER -v "$@"
    exit $?
fi

# Without arguments: the full suite, in the same separate batches as the CI
# (.github/workflows/tests.yml). Loading QtMultimedia (ambiance, MainWindow)
# before torch in one process segfaults on some setups (TICKET-067).
QT_MULTIMEDIA_TESTS="tests/test_ambiance_manager.py tests/test_help_system_mod.py tests/test_mods_dialog_ui.py tests/test_settings_dialog.py tests/test_sillytavern_mod.py"
IGNORES=""
for f in $QT_MULTIMEDIA_TESTS; do IGNORES="$IGNORES --ignore=$f"; done

STATUS=0
echo "Running tests (main batch)..."
$RUNNER -q tests/ $IGNORES || STATUS=1
echo "Running tests (Qt multimedia batch)..."
$RUNNER -q $QT_MULTIMEDIA_TESTS || STATUS=1
echo "Running tests (mods batch)..."
$RUNNER -q mods/*/tests -p tests.conftest || STATUS=1
exit $STATUS
