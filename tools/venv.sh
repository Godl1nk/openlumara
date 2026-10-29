# shared helpers for install.sh, run.sh and update.sh
#
# The caller changes to the repository root before sourcing this file, so
# every path below is relative to it.
#
# The python environment lives in .venv/ for both uv and the plain pip
# fallback, so an environment built by either one stays usable when the
# other tool shows up later.
#
# venv/ is the legacy name from before uv was supported. migrate_venv
# copies it to .venv/ and fixes up the absolute paths inside it, so the
# packages that are already installed are kept instead of being
# downloaded again. The old directory is left in place as a fallback.

# minimum python version Openlumara runs on
MIN_PY="3.12"

# is $1 a python new enough to run Openlumara?
py_ok() {
    command -v "$1" >/dev/null 2>&1 || return 1
    "$1" -c "import sys; sys.exit(0 if sys.version_info >= tuple(int(x) for x in '${MIN_PY}'.split('.')) else 1)" 2>/dev/null
}

# does uv manage the environment?
have_uv() {
    command -v uv >/dev/null 2>&1
}

# sync the environment with uv
uv_sync() {
    # honour the interpreter the caller picked, so uv and the pip fallback
    # end up using the same one
    if [ -n "${PYTHON_BIN:-}" ]; then
        UV_PYTHON="$PYTHON_BIN"
        export UV_PYTHON
    fi

    # --inexact keeps module dependencies the app installed at runtime
    uv sync --frozen --inexact --extra webui --extra channels --extra modules
}

# pick an interpreter new enough to run Openlumara, into $PYTHON
find_python() {
    if [ -n "${PYTHON_BIN:-}" ] && py_ok "$PYTHON_BIN"; then
        PYTHON="$PYTHON_BIN"
        return 0
    fi

    for cand in python3.13 python3.12 python3 python; do
        if py_ok "$cand"; then
            PYTHON="$cand"
            return 0
        fi
    done
    return 1
}

# complain when there is no python to build an environment with
require_python() {
    if find_python; then
        return 0
    fi

    echo "error: no python ${MIN_PY}+ found (checked python3.13, python3.12, python3, python)"
    echo "       hint: use the quick installer, it installs python for you:"
    echo "             curl -fsSL https://raw.githubusercontent.com/Rose22/openlumara/main/curl.sh | sh"
    return 1
}

# copy a legacy venv/ to .venv/ and fix up the paths inside it
migrate_venv() {
    if [ ! -d venv ] || [ -d .venv ]; then
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

    echo "migrating venv/ to .venv/ ..."

    # uv discards a project environment whose interpreter is too old for
    # requires-python, taking the installed packages with it. check first
    # so the user is not surprised by a silent rebuild.
    if [ -x "venv/bin/python" ] && ! py_ok "venv/bin/python"; then
        echo "warning: venv/ was built with a python older than ${MIN_PY};"
        echo "         uv will rebuild the environment from scratch"
    fi

    # copy rather than move: the old venv stays usable as a fallback, and
    # nothing is lost if uv decides to rebuild the environment anyway
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

    echo "migrated venv/ -> .venv/ - the installed packages are kept"
    echo "the old venv/ still works as a fallback; delete it when you're happy"
}

# create the environment from scratch
create_venv() {
    echo "setting up virtual environment with $PYTHON ($($PYTHON -c 'import platform; print(platform.python_version())'))..."
    "$PYTHON" -m venv .venv || return 1
    .venv/bin/pip install --upgrade pip || return 1
}

# install the pinned requirements into the environment
install_deps() {
    .venv/bin/python tools/dump_requirements.py --groups webui,channels,modules --output .venv/requirements.txt || return 1
    .venv/bin/pip install -r .venv/requirements.txt
}

# make sure the environment is ready to run the app
#
# the requirements are installed when the environment is created; pass
# "update" to install them even when the environment already existed
ensure_venv() {
    if [ ! -x .venv/bin/python ]; then
        require_python || return 1
        create_venv || return 1
    elif [ "${1:-}" != "update" ]; then
        return 0
    fi

    install_deps
}
