#!/bin/sh
# the repository root is the directory this script lives in
cd "$(dirname "$0")" || exit 1

# Configure the remote only when it's missing. Forcing the URL on every run
# would fight a renamed repository or a mirror.
if ! git remote get-url origin >/dev/null 2>&1; then
    git remote add origin https://github.com/Godl1nk/openlumara.git 2>/dev/null
fi

echo "checking for updates..."
# -- AI GENERATED CODE (GPT-6.2-Sol) :: 2026-11-25 07:33 +08:00 harness:Codex
git pull --ff-only || exit $?

# Read the dependency helpers from the updated checkout.
. tools/venv.sh
echo "ensuring dependencies are up to date..."
if have_uv; then
    uv_sync || exit 1
else
    ensure_venv update || exit 1
fi

echo
echo "done!"
