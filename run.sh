#!/bin/bash

# first run? set up the venv via install.sh, then continue
if [ ! -x "venv/bin/python" ]; then
    sh ./install.sh || exit 1
fi

# aaand run!
source venv/bin/activate
exec python main.py "$@"
