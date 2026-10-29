#!/bin/bash
# resolve this script's real location
target="$0"
while [ -L "$target" ]; do
    link=$(readlink "$target")
    case "$link" in
        /*) target="$link" ;;
        *)  target="$(dirname "$target")/$link" ;;
    esac
done
cd "$(dirname "$target")" || exit 1

# shared helpers: the environment lives in .venv/ for both uv and the pip
# fallback, and venv/ is the legacy name from before uv was supported
. tools/venv.sh

# uv manages the environment when available, plain venv + pip otherwise
if command -v uv >/dev/null 2>&1; then
    # --inexact keeps module dependencies the app installed at runtime
    uv sync --frozen --inexact --extra webui --extra channels --extra modules || exit 1
    exec uv run --frozen --no-sync main.py "$@"
fi

if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "error: no python binary found (checked python3 and python)"
    exit 1
fi

# a legacy venv/ is copied to .venv/ so the packages that are already
# installed are kept instead of being downloaded again
migrate_venv

if [ ! -d ".venv" ]; then
    echo "uv not found, setting up virtual environment with $PYTHON_BIN..."
    $PYTHON_BIN -m venv .venv || exit 1
    .venv/bin/python tools/dump_requirements.py --groups webui,channels,modules --output .venv/requirements.txt || exit 1
    .venv/bin/pip install -r .venv/requirements.txt || exit 1
fi

exec .venv/bin/python main.py "$@"
