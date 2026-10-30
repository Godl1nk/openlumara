#!/bin/bash
# install.sh symlinks this script into ~/.local/bin as `openlumara`, so follow
# the link back to the repository before touching any relative path
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

# a venv/ from before uv was supported is left alone; the environment
# below is built from scratch in .venv/
note_legacy_venv

# uv manages the environment when available, plain venv + pip otherwise
if have_uv; then
    uv_sync || exit 1
    exec uv run --frozen --no-sync main.py "$@"
fi

ensure_venv || exit 1
exec .venv/bin/python main.py "$@"
