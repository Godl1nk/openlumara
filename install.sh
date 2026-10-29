#!/bin/sh
#   usage: sh install.sh [--reinstall]
#   --reinstall   discard the existing venv and build a fresh one
# env: PYTHON_BIN=<path>  use this interpreter instead of auto-detecting

# -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-26) harness:openlumara
set -eu
cd "$(dirname "$0")"

# expose an `openlumara` command by symlinking run.sh into ~/.local/bin
# (done before the venv early-exit so re-running install.sh also repairs it)
setup_command() {
    BIN_DIR="$HOME/.local/bin"
    LINK="$BIN_DIR/openlumara"
    TARGET="$(pwd)/run.sh"
    mkdir -p "$BIN_DIR"
    if [ -L "$LINK" ]; then
        rm -f "$LINK"
        ln -s "$TARGET" "$LINK"
    elif [ -e "$LINK" ]; then
        echo "note: $LINK already exists and is not a symlink - leaving it alone"
    else
        ln -s "$TARGET" "$LINK"
    fi

    # make sure ~/.local/bin is on PATH for future shells (macOS notably lacks it)
    case ":$PATH:" in
        *":$BIN_DIR:"*) ;;
        *)
            for rc in "$HOME/.profile" "$HOME/.zshrc"; do
                if [ "$rc" = "$HOME/.zshrc" ] && [ ! -f "$rc" ] && [ "$(uname)" != "Darwin" ]; then
                    continue
                fi
                grep -q '.local/bin' "$rc" 2>/dev/null || {
                    printf '\n# added by OpenLumara installer\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$rc"
                }
            done
            echo "added ~/.local/bin to PATH - reopen your shell, or run:"
            echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
            ;;
    esac
}
setup_command

# find a python new enough for OpenLumara (3.12+)
MIN_PY="3.12"
py_ok() {
    command -v "$1" >/dev/null 2>&1 || return 1
    "$1" -c "import sys; sys.exit(0 if sys.version_info >= tuple(int(x) for x in '${MIN_PY}'.split('.')) else 1)" 2>/dev/null
}

# pre-uv installs kept the environment in venv/; uv expects .venv/
# copy it over so uv adopts the packages that are already installed
migrate_venv() {
    if [ ! -d venv ]; then
        return 0
    fi
    if [ -d .venv ]; then
        echo "note: venv/ and .venv/ both exist - keeping both"
        echo "      (delete venv/ when you no longer need it)"
        return 0
    fi

    old="$(pwd)/venv"
    new="$(pwd)/.venv"

    # the paths are matched literally, so everything that is not a letter
    # or a digit has to be escaped before it goes into a sed pattern.
    # the same escaping makes the replacement safe: & and \ are special
    # there, and a path may well contain them.
    old_pat="$(printf '%s' "$old" | sed -e 's/[^a-zA-Z0-9]/\\&/g')"
    new_pat="$(printf '%s' "$new" | sed -e 's/[^a-zA-Z0-9]/\\&/g')"

    # uv discards a project environment whose interpreter is too old for
    # requires-python, taking the installed packages with it. check first
    # so the user is not surprised by a silent rebuild.
    if [ -x "venv/bin/python" ] && ! py_ok "venv/bin/python"; then
        echo "warning: venv/ was built with a python older than ${MIN_PY};"
        echo "         uv will rebuild the environment from scratch"
    fi

    # copy rather than move: the old venv stays usable as a fallback, and
    # nothing is lost if uv decides to rebuild the environment anyway
    echo "copying venv/ to .venv/ ..."
    cp -a venv .venv

    # Two kinds of file in .venv/bin carry the old path, and they need
    # different handling:
    #
    #   * console scripts carry it in the shebang, on line 1
    #   * the activate scripts carry it in the body (VIRTUAL_ENV=...)
    #
    # The first pass touches line 1 only, so it cannot fix the activate
    # scripts: their line 1 is a comment, so the guard never matches them.
    # Hence the separate second pass below. Restricting the first pass to
    # line 1 also keeps it safe for anything else in bin/ that is not
    # text, since a whole-file rewrite would corrupt it.
    for f in .venv/bin/*; do
        # skip symlinks: those are the interpreter itself, and rewriting
        # one would touch the real python installation
        if [ -L "$f" ] || [ ! -f "$f" ]; then
            continue
        fi
        if head -1 "$f" 2>/dev/null | grep -qF "$old"; then
            sed "1s|$old_pat|$new_pat|" "$f" > "$f.tmp" 2>/dev/null \
                && cat "$f.tmp" > "$f" && rm -f "$f.tmp"
        fi
    done

    # The activate scripts are written by the venv module and are always
    # these three. The path is not on their first line, so the pass above
    # skipped them; rewrite every occurrence in them.
    for f in .venv/bin/activate .venv/bin/activate.csh .venv/bin/activate.fish; do
        if [ -f "$f" ]; then
            sed "s|$old_pat|$new_pat|g" "$f" > "$f.tmp" 2>/dev/null \
                && cat "$f.tmp" > "$f" && rm -f "$f.tmp"
        fi
    done

    echo "copied venv/ -> .venv/ - uv keeps the installed packages"
    echo "the old venv/ still works as a fallback; delete it when you're happy"
}

# uv manages the environment when available, plain venv + pip otherwise
if command -v uv >/dev/null 2>&1; then
    if [ "${1:-}" = "--reinstall" ]; then
        echo "removing existing environment..."
        rm -rf .venv venv
    else
        migrate_venv
    fi

    # honour PYTHON_BIN so the interpreter matches the one the caller picked
    if [ -n "${PYTHON_BIN:-}" ]; then
        UV_PYTHON="$PYTHON_BIN"
        export UV_PYTHON
    fi

    echo "setting up the environment with uv..."
    # --inexact keeps module dependencies the app installed at runtime
    uv sync --frozen --inexact --extra webui --extra channels --extra modules || exit 1

    echo "done! start OpenLumara with: openlumara   (or ./run.sh)"
    exit 0
fi

if [ "${1:-}" = "--reinstall" ]; then
    echo "removing existing venv..."
    rm -rf venv
fi

if [ -x "venv/bin/python" ]; then
    echo "venv already set up - nothing to do (use --reinstall to rebuild)"
    echo "start OpenLumara with: openlumara   (or ./run.sh)"
    exit 0
fi

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
venv/bin/python tools/dump_requirements.py --groups webui,channels,modules --output venv/requirements.txt
venv/bin/pip install -r venv/requirements.txt

echo "done! start OpenLumara with: openlumara   (or ./run.sh)"
