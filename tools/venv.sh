# shared helper for install.sh, run.sh and update.sh
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

py_ok() {
    command -v "$1" >/dev/null 2>&1 || return 1
    "$1" -c "import sys; sys.exit(0 if sys.version_info >= tuple(int(x) for x in '${MIN_PY}'.split('.')) else 1)" 2>/dev/null
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
