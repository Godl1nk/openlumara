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

# first run? set up the venv via install.sh, then continue
if [ ! -x "venv/bin/python" ]; then
    sh ./install.sh || exit 1
fi

# aaand run!
source venv/bin/activate
exec python main.py "$@"
