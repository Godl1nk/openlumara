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

echo "checking for updates..."
if git fetch origin 2>/dev/null; then
    if git rev-parse --abbrev-ref @{u} >/dev/null 2>&1; then
        LOCAL=$(git rev-parse HEAD)
        REMOTE=$(git rev-parse @{u})

        if [ "$LOCAL" != "$REMOTE" ]; then
            echo "updates available! pulling changes..."
            git pull
        else
            echo "already up to date."
        fi
    else
        echo "no upstream configured, skipping update check."
    fi
else
    echo "warning: git fetch failed. skipping update check."
fi

echo "ensuring dependencies are up to date..."
if have_uv; then
    uv_sync || exit 1
else
    # the requirements are reinstalled, so a changed requirements.txt is
    # picked up even when the environment already existed
    ensure_venv update || exit 1
fi

echo
echo "done!"
