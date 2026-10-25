#!/bin/bash

# work from the repo this script lives in, even when invoked from elsewhere
cd "$(dirname "$0")" || exit 1

# Configure the remote only when it's missing. Forcing the URL on every run
# would fight a renamed repository or a mirror.
if ! git remote get-url origin >/dev/null 2>&1; then
    git remote add origin https://github.com/Godl1nk/openlumara.git 2>/dev/null
fi

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

PYTHON_BIN="${PYTHON_BIN:-python3}"
if [ ! -d "venv" ]; then
    echo "setting up virtual environment with $PYTHON_BIN..."
    $PYTHON_BIN -m venv venv
fi

echo "ensuring dependencies are up to date..."
source venv/bin/activate
pip install -q --upgrade pip

# Check if requirements.txt has changed before installing
if [ -f ".requirements_hash" ] && [ -f "requirements.txt" ]; then
    OLD_HASH=$(cat .requirements_hash)
    NEW_HASH=$(sha256sum requirements.txt | awk '{print $1}')
    if [ "$OLD_HASH" = "$NEW_HASH" ]; then
        echo "requirements.txt unchanged, skipping pip install."
    else
        echo "requirements.txt changed, updating dependencies..."
        pip install -r requirements.txt
        echo "$NEW_HASH" > .requirements_hash
    fi
else
    echo "requirements.txt changed (or first run), updating dependencies..."
    pip install -r requirements.txt
    if [ -f "requirements.txt" ]; then
        sha256sum requirements.txt | awk '{print $1}' > .requirements_hash
    fi
fi

echo
echo "done!"
