#!/bin/bash
# resolve this script's real location, so it works from anywhere
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

# a legacy venv/ is copied to .venv/ so the packages that are already
# installed are kept instead of being downloaded again
migrate_venv || exit 1

# uv manages the environment when available, plain venv + pip otherwise
if have_uv; then
    uv_sync || exit 1
    exec uv run --frozen --no-sync main.py "$@"
fi

ensure_venv || exit 1
exec .venv/bin/python main.py "$@"
