#!/bin/sh
#   usage: sh install.sh [--reinstall]
#   --reinstall   discard the existing venv and build a fresh one
# env: PYTHON_BIN=<path>  use this interpreter instead of auto-detecting

set -eu
cd "$(dirname "$0")"

if [ "${1:-}" = "--reinstall" ]; then
    echo "removing existing venv..."
    rm -rf venv
fi

if [ -x "venv/bin/python" ]; then
    echo "venv already set up - nothing to do (use --reinstall to rebuild)"
    exit 0
fi

# find a python new enough for OpenLumara (3.12+)
MIN_PY="3.12"
py_ok() {
    command -v "$1" >/dev/null 2>&1 || return 1
    "$1" -c "import sys; sys.exit(0 if sys.version_info >= tuple(int(x) for x in '${MIN_PY}'.split('.')) else 1)" 2>/dev/null
}

if [ -n "${PYTHON_BIN:-}" ] && py_ok "$PYTHON_BIN"; then
    :
else
    PYTHON_BIN=""
    for cand in python3.13 python3.12 python3 python; do
        if py_ok "$cand"; then PYTHON_BIN="$cand"; break; fi
    done
fi

if [ -z "$PYTHON_BIN" ]; then
    echo "error: no python ${MIN_PY}+ found (checked python3.13, python3.12, python3, python)"
    echo "       hint: use the quick installer, it installs python for you:"
    echo "             curl -fsSL https://raw.githubusercontent.com/Rose22/openlumara/main/curl.sh | sh"
    exit 1
fi

echo "setting up virtual environment with $PYTHON_BIN ($($PYTHON_BIN -c 'import platform; print(platform.python_version())'))..."
"$PYTHON_BIN" -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt

echo "done! start OpenLumara with: ./run.sh"
