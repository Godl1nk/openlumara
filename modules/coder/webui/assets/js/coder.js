/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
   coder sidebar (sandbox dropdown + lazy file tree) and file edit modal.
   Talks to /api/ext/coder/. the tree is kept flat (rows with depth) so
   alpine renders it with one x-for; children lazy-load on first expand. */

/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
   the file edit modal is CodeMirror 5, vendored under assets/vendor/.
   vendor/ deliberately sits OUTSIDE assets/css + assets/js so the webui
   channel's auto-discovery never force-loads it on every page: the
   library is lazy-loaded (sequentially - addons depend on the core, some
   modes/addons on others) the first time a file is opened, then kept
   warm for the rest of the page's life. */
const CM_BASE = "/ext-assets/coder/vendor/codemirror/";

const CM_CSS = [
    "lib/codemirror.css",
    "addon/dialog/dialog.css",
    "addon/fold/foldgutter.css",
    "addon/search/matchesonscrollbar.css",
];

const CM_JS = [
    "lib/codemirror.js",
    "addon/comment/comment.js",
    "addon/dialog/dialog.js",
    "addon/search/searchcursor.js",
    "addon/search/search.js",
    "addon/scroll/annotatescrollbar.js",
    "addon/search/matchesonscrollbar.js",
    "addon/edit/matchbrackets.js",
    "addon/edit/closebrackets.js",
    "addon/edit/closetag.js",
    "addon/edit/continuelist.js",
    "addon/edit/trailingspace.js",
    "addon/selection/active-line.js",
    "addon/fold/foldcode.js",
    "addon/fold/foldgutter.js",
    "addon/fold/brace-fold.js",
    "addon/fold/comment-fold.js",
    "addon/fold/indent-fold.js",
    "addon/fold/xml-fold.js",
    "mode/xml/xml.js",
    "mode/css/css.js",
    "mode/javascript/javascript.js",
    "mode/htmlmixed/htmlmixed.js",
    "mode/jinja2/jinja2.js",
    "mode/markdown/markdown.js",
    "mode/python/python.js",
    "mode/shell/shell.js",
    "mode/yaml/yaml.js",
    "mode/toml/toml.js",
    "mode/properties/properties.js",
];

// the live editor instance lives OUTSIDE the Alpine store on purpose:
// a reactive proxy wrapped around a whole CodeMirror would be a world
// of hurt, and nothing in the templates needs to read it.
let CODER_CM = null;
let CODER_CM_LOAD = null;

function coderLoadScript(src) {
    return new Promise((resolve, reject) => {
        const s = document.createElement("script");
        s.src = src;
        s.onload = resolve;
        s.onerror = () => reject(new Error("failed to load " + src));
        document.head.appendChild(s);
    });
}

function coderLoadCss(href) {
    return new Promise((resolve, reject) => {
        const l = document.createElement("link");
        l.rel = "stylesheet";
        l.href = href;
        l.onload = resolve;
        l.onerror = () => reject(new Error("failed to load " + href));
        document.head.appendChild(l);
    });
}

function coderLoadCodeMirror() {
    if (!CODER_CM_LOAD) {
        CODER_CM_LOAD = (async () => {
            await Promise.all(CM_CSS.map((f) => coderLoadCss(CM_BASE + f)));
            // sequential: script order IS dependency order here
            for (const f of CM_JS) {
                await coderLoadScript(CM_BASE + f);
            }
            return window.CodeMirror;
        })().catch((e) => {
            CODER_CM_LOAD = null; // allow a retry on the next open
            throw e;
        });
    }
    return CODER_CM_LOAD;
}

// theme classes defined in coder.css, palette-matched to the
// github-dark/light code themes the chat uses
function coderThemeName() {
    const theme = Alpine.store("theme");
    return theme && theme.mode === "light" ? "lumara-light" : "lumara";
}

const CODER_PANEL = {
    sandboxes: [],
    sandbox: "",
    read_only: false,
    rows: [],
    expanded: {},
    children: {},
    rootEntries: null,
    loading: false,
    loaded: false,
    error: "",
    editor: { path: "", content: "", mode: "", dirty: false, saving: false, error: "", saved: "", cmReady: false },
    caretLine: 1,
    caretCol: 1,
    selLen: 0,
    _reveal: 0, // line to jump to once the loaded file is in the editor
    _silent: false, // set while swapping files in (keeps change events from dirtying)

    // right-click menu + small name-prompt modal (create/rename/move)
    menu: { open: false, x: 0, y: 0, row: null },
    prompt: { mode: "", title: "", hint: "", value: "", submitting: false, error: "", row: null, parent: "" },

    // in-sidebar recursive search (replaces the tree view while active)
    search: { active: false, query: "", regex: false, running: false, results: [], truncated: false, error: "", done: false },

    // fuzzy quick-open (ctrl+p)
    quick: { query: "", idx: 0, files: [], filesLoadedFor: "" },

    // drag & drop moving
    dragPath: "",
    dropTarget: null,

    async refresh(force = false) {
        if (!this.sandboxes.length || force) {
            await this.loadSandboxes();
        }

        if (this.sandbox && (force || !this.loaded)) {
            await this.loadRoot();
        }
    },

    async loadSandboxes() {
        try {
            const data = await simpleApiFetch("/api/ext/coder/sandboxes") || {};
            this.sandboxes = data.sandboxes || [];
            this.read_only = !!data.read_only;
        } catch (e) {
            this.sandboxes = [];
        }

        // selection vanished (sandbox removed from config): fall back
        if (this.sandbox && !this.sandboxes.includes(this.sandbox)) {
            this.sandbox = "";
        }

        if (!this.sandbox && this.sandboxes.length) {
            // prefer the sandbox chosen before a page reload over the
            // plain first entry
            const saved = localStorage.getItem("coder_sandbox") || "";
            this.sandbox = this.sandboxes.includes(saved) ? saved : this.sandboxes[0];
        }
    },

    async onSandboxChange() {
        try { localStorage.setItem("coder_sandbox", this.sandbox); } catch (e) {}
        this.expanded = {};
        this.children = {};
        this.rootEntries = null;
        this.rows = [];
        this.loaded = false;
        this.quick.filesLoadedFor = "";
        this.quick.files = [];
        this.clearSearch();

        if (this.sandbox) {
            await this.loadRoot();
        }
    },

    async loadRoot() {
        this.loading = true;
        this.error = "";

        try {
            const data = await simpleApiFetch(`/api/ext/coder/tree?sandbox=${encodeURIComponent(this.sandbox)}&path=`);
            this.rootEntries = data.entries || [];
            this.loaded = true;
            this.rebuild();
        } catch (e) {
            this.error = this.errorText(e);
            this.rootEntries = [];
            this.rebuild();
        } finally {
            this.loading = false;
        }
    },

    rebuild() {
        const out = [];

        const walk = (entries, depth) => {
            for (const entry of entries) {
                out.push({
                    path: entry.path,
                    name: entry.name,
                    is_dir: entry.is_dir,
                    hidden: entry.hidden,
                    blacklisted: entry.blacklisted,
                    depth: depth,
                });

                if (entry.is_dir && this.expanded[entry.path] && this.children[entry.path]) {
                    walk(this.children[entry.path], depth + 1);
                }
            }
        };

        walk(this.rootEntries || [], 0);
        this.rows = out;
    },

    async toggle(row) {
        if (this.children[row.path] == null) {
            this.loading = true;
            try {
                const data = await simpleApiFetch(`/api/ext/coder/tree?sandbox=${encodeURIComponent(this.sandbox)}&path=${encodeURIComponent(row.path)}`);
                this.children[row.path] = data.entries || [];
            } catch (e) {
                this.error = this.errorText(e);
                this.children[row.path] = [];
            } finally {
                this.loading = false;
            }
        }

        if (this.expanded[row.path]) {
            delete this.expanded[row.path];
        } else {
            this.expanded[row.path] = true;
        }

        this.rebuild();
    },

    async openFile(row, line) {
        const path = row.path;
        this.editor = { path: path, content: "", mode: "", dirty: false, saving: false, error: "", saved: "", cmReady: !!CODER_CM };
        this._reveal = line && line > 1 ? line : 0;
        this.caretLine = this._reveal || 1;
        this.caretCol = 1;
        this.selLen = 0;

        // always (re-)open: no-op when already mounted, and cancels a close
        // requested in the same tick (quick-open calls closeModal then
        // openFile; if Alpine flushed the unmount in between, the new file
        // would otherwise have no modal to open in)
        Alpine.store("ui").openModal("coder_file");

        try {
            const data = await simpleApiFetch(`/api/ext/coder/read?sandbox=${encodeURIComponent(this.sandbox)}&path=${encodeURIComponent(path)}`);
            const content = data.content || "";
            this.editor.content = content;
            this.editor.mode = this.detectLang(path, content);
            this.loadFileIntoCm(content);
            this.revealPending();
        } catch (e) {
            this.editor.error = this.errorText(e);
        }
    },

    // swap a freshly-fetched file into a live editor (modal was already open)
    loadFileIntoCm(content) {
        if (!CODER_CM) return;

        this._silent = true;
        CODER_CM.setValue(content);
        CODER_CM.setOption("mode", this.editor.mode || null);
        CODER_CM.clearHistory();
        this._silent = false;
    },

    // jump to the pending line (search results / reveal requests)
    revealPending() {
        if (!CODER_CM || !this._reveal) return;

        // still fetching: an empty editor would clamp the request to the
        // top and eat it. openFile calls back into here once content lands
        if (!this.editor.content && !this.editor.error) return;

        const line = Math.max(0, Math.min(this._reveal - 1, CODER_CM.lineCount() - 1));
        CODER_CM.setCursor({ line: line, ch: 0 });
        CODER_CM.scrollIntoView({ line: line, ch: 0 }, 120);
        CODER_CM.focus();
        this._reveal = 0;
    },

    /* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
       CodeMirror mode for a file: extension map first, then a confident
       highlightAuto guess (hljs is already loaded globally) mapped onto the
       vendored modes, else plaintext. resolved ONCE on open. */
    detectLang(path, code) {
        const map = {
            py: "python", pyw: "python",
            js: "javascript", mjs: "javascript", cjs: "javascript", jsx: "javascript",
            json: "javascript", jsonl: "javascript",
            html: "htmlmixed", htm: "htmlmixed",
            xml: "xml", svg: "xml", xsl: "xml", rss: "xml", atom: "xml",
            j2: "jinja2", jinja: "jinja2",
            css: "css", scss: "css",
            md: "markdown", markdown: "markdown",
            yml: "yaml", yaml: "yaml",
            sh: "shell", bash: "shell", zsh: "shell",
            toml: "toml",
            ini: "properties", cfg: "properties", properties: "properties", env: "properties",
            txt: "",
        };

        const ext = path.includes(".") ? path.split(".").pop().toLowerCase() : "";
        if (map[ext] !== undefined) return map[ext];

        const guessMap = {
            python: "python", javascript: "javascript", json: "javascript",
            xml: "xml", html: "htmlmixed", css: "css", scss: "css",
            markdown: "markdown", yaml: "yaml", shell: "shell", bash: "shell",
            ini: "properties", toml: "toml",
        };

        if (typeof hljs === "undefined" || !code) return "";

        try {
            const res = hljs.highlightAuto(code);
            if (res.language && res.relevance >= 8 && guessMap[res.language]) {
                return guessMap[res.language];
            }
        } catch (e) {}

        return "";
    },

    /* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
       CodeMirror lifecycle. initEditor runs from the modal's x-init once
       the lazy library load resolves (guarded against the modal closing
       mid-load); destroyEditor runs from Alpine's cleanup() on unmount.
       everything CodeMirror does natively now: line numbers (wrap-aware),
       active line, bracket matching/closing, folding, incremental search
       (ctrl+f/ctrl+h via the dialog addon), comment toggling, undo. */
    async initEditor(host) {
        try {
            await coderLoadCodeMirror();
        } catch (e) {
            this.editor.error = "could not load the code editor (" + this.errorText(e) + ")";
            return;
        }

        // closed while the library was loading
        if (!host.isConnected) return;

        const cm = CodeMirror(host, {
            value: this.editor.content,
            mode: this.editor.mode || null,
            theme: coderThemeName(),
            lineNumbers: true,
            lineWrapping: true,
            styleActiveLine: true,
            matchBrackets: true,
            autoCloseBrackets: !this.read_only,
            autoCloseTags: !this.read_only,
            showTrailingSpace: !this.read_only,
            indentUnit: 4,
            tabSize: 4,
            smartIndent: true,
            readOnly: !!this.read_only,
            foldGutter: true,
            gutters: ["CodeMirror-linenumbers", "CodeMirror-foldgutter"],
            extraKeys: {
                "Ctrl-S": () => this.save(),
                "Cmd-S": () => this.save(),
                "Ctrl-F": "find",
                "Cmd-F": "find",
                "F3": "findNext",
                "Shift-F3": "findPrev",
                "Ctrl-G": "findNext",
                "Cmd-G": "findNext",
                "Shift-Ctrl-G": "findPrev",
                "Shift-Cmd-G": "findPrev",
                "Ctrl-H": "replace",
                "Cmd-Alt-F": "replace",
                "Ctrl-/": "toggleComment",
                "Cmd-/": "toggleComment",
                // keep markdown lists going on Enter, everything else normal.
                // (must execCommand directly: CM5 treats a function binding's
                // return value as "handled", not as a command name)
                "Enter": (editor) => {
                    editor.execCommand(
                        editor.getOption("mode") === "markdown"
                            ? "newlineAndIndentContinueMarkdownList"
                            : "newlineAndIndent"
                    );
                },
            },
        });

        CODER_CM = cm;
        this.editor.cmReady = true;

        cm.on("change", () => {
            if (!this._silent && !this.editor.dirty) this.editor.dirty = true;
        });

        cm.on("cursorActivity", (c) => {
            const cur = c.getCursor();
            this.caretLine = cur.line + 1;
            this.caretCol = cur.ch + 1;
            this.selLen = c.somethingSelected() ? c.getSelection().length : 0;
        });

        // follow dark/light switches while the modal stays open
        const onTheme = () => cm.setOption("theme", coderThemeName());
        window.addEventListener("theme-changed", onTheme);
        cm._coderThemeOff = () => window.removeEventListener("theme-changed", onTheme);

        this.revealPending();
        cm.focus();
    },

    destroyEditor() {
        if (CODER_CM) {
            try {
                CODER_CM._coderThemeOff();
            } catch (e) {}
            // the editor's DOM goes away with the modal unmount; dropping the
            // reference is all the teardown a GC'd CodeMirror needs
            CODER_CM = null;
        }
        this.editor.cmReady = false;
    },

    /* ---- right-click context menu ---- */
    openMenu(event, row) {
        if (this.read_only) return;

        // both entry types now show nearly the same item count; use the
        // taller estimate so the menu never overflows the viewport edge
        const menuH = 300;
        this.menu = {
            open: true,
            x: Math.max(4, Math.min(event.clientX, window.innerWidth - 190)),
            y: Math.max(4, Math.min(event.clientY, window.innerHeight - menuH)),
            row: row,
        };
    },

    closeMenu() {
        this.menu.open = false;
    },

    menuAction(fn) {
        const row = this.menu.row;
        this.closeMenu();
        if (row) fn(row);
    },

    /* ---- small prompt modal (new file / new folder / rename / move) ---- */
    openPrompt(mode, row) {
        const parent = row.is_dir ? row.path : row.path.split("/").slice(0, -1).join("/");
        let title = "", value = "", hint = "";

        // where the new entry will actually land (files: their parent folder)
        const inPath = parent ? `${this.sandbox}/${parent}` : this.sandbox;

        if (mode === "new_file") { title = `New file in ${inPath}`; hint = "filename, e.g. notes.py"; }
        if (mode === "new_folder") { title = `New folder in ${inPath}`; hint = "folder name"; }
        if (mode === "rename") { title = `Rename ${row.name}`; value = row.name; hint = "new name"; }
        if (mode === "move") { title = `Move ${row.name}`; value = row.path; hint = "new path within the sandbox"; }

        this.prompt = { mode, title, hint, value, submitting: false, error: "", row: row, parent };
        Alpine.store("ui").openModal("coder_prompt");
    },

    closePrompt() {
        this.prompt = { mode: "", title: "", hint: "", value: "", submitting: false, error: "", row: null, parent: "" };
        Alpine.store("ui").closeModal();
    },

    async submitPrompt() {
        const p = this.prompt;
        if (!p.mode || p.submitting) return;

        const name = (p.value || "").trim();
        if (!name) { p.error = "name can't be empty"; return; }
        if (name === "." || name === "..") { p.error = "nice try"; return; }
        if ((p.mode === "new_file" || p.mode === "new_folder" || p.mode === "rename") && name.includes("/")) {
            p.error = "just a plain name here, no path separators";
            return;
        }

        p.submitting = true;
        p.error = "";

        try {
            if (p.mode === "new_file" || p.mode === "new_folder") {
                const target = p.parent ? p.parent + "/" + name : name;
                await simpleApiPost("/api/ext/coder/create", { sandbox: this.sandbox, path: target, is_dir: p.mode === "new_folder" });
                if (p.parent) this.expanded[p.parent] = true;
                await this.reloadAfterChange([p.parent]);
            } else if (p.mode === "rename") {
                const parent = p.row.path.split("/").slice(0, -1).join("/");
                const target = parent ? parent + "/" + name : name;
                await simpleApiPost("/api/ext/coder/move", { sandbox: this.sandbox, src: p.row.path, dst: target });
                if (this.editor.path === p.row.path) this.editor.path = target;
                await this.reloadAfterChange([parent]);
            } else if (p.mode === "move") {
                const oldParent = p.row.path.split("/").slice(0, -1).join("/");
                const dst = name.replace(/^\/+/, "").replace(/\/+$/, "");
                const newParent = dst.includes("/") ? dst.split("/").slice(0, -1).join("/") : "";
                await simpleApiPost("/api/ext/coder/move", { sandbox: this.sandbox, src: p.row.path, dst });
                if (this.editor.path === p.row.path) this.editor.path = dst;
                await this.reloadAfterChange([oldParent, newParent]);
            }

            this.closePrompt();
        } catch (e) {
            p.error = this.errorText(e);
        } finally {
            p.submitting = false;
        }
    },

    async deleteRow(row) {
        const what = row.is_dir ? "folder" : "file";
        const extra = row.is_dir ? " Everything inside it will be removed too." : "";
        if (!window.confirm(`Delete ${what} ${row.path}?${extra}`)) return;

        try {
            await simpleApiPost("/api/ext/coder/delete", { sandbox: this.sandbox, path: row.path });

            if (this.editor.path === row.path || this.editor.path.startsWith(row.path + "/")) {
                this.editor = { path: "", content: "", mode: "", dirty: false, saving: false, error: "", saved: "", cmReady: false };
                if (Alpine.store("ui").currentModal === "coder_file") Alpine.store("ui").closeModal();
            }

            await this.reloadAfterChange([row.path.split("/").slice(0, -1).join("/")]);
        } catch (e) {
            this.error = this.errorText(e);
        }
    },

    // targeted tree refresh after a filesystem change: re-fetch the given
    // folders' children, then rebuild from the root. expansion state is
    // preserved; unaffected cached folders keep their (still valid) children.
    async reloadAfterChange(forceFolders) {
        for (const folder of forceFolders || []) {
            if (!folder) continue;
            try {
                const data = await simpleApiFetch(`/api/ext/coder/tree?sandbox=${encodeURIComponent(this.sandbox)}&path=${encodeURIComponent(folder)}`);
                this.children[folder] = data.entries || [];
            } catch (e) {
                this.children[folder] = [];
            }
        }

        await this.loadRoot();
    },

    async save() {
        if (this.editor.saving || this.read_only) return;

        // while the editor is live, CodeMirror holds the true content
        const content = CODER_CM ? CODER_CM.getValue() : this.editor.content;

        this.editor.saving = true;
        this.editor.error = "";

        try {
            await simpleApiPost("/api/ext/coder/save", {
                sandbox: this.sandbox,
                path: this.editor.path,
                content: content,
            });

            this.editor.content = content;
            this.editor.dirty = false;
            this.editor.saved = "saved ✓";
        } catch (e) {
            if (e && typeof e === "object" && e.errors) {
                this.editor.error = (e.message ? e.message + "\n" : "") + e.errors.join("\n");
            } else {
                this.editor.error = this.errorText(e);
            }
        } finally {
            this.editor.saving = false;
        }
    },

    closeEditor() {
        if (this.editor.dirty && !window.confirm("This file has unsaved changes. Close anyway?")) {
            return;
        }

        this.editor = { path: "", content: "", mode: "", dirty: false, saving: false, error: "", saved: "", cmReady: false };
        Alpine.store("ui").closeModal();
    },

    /* ---- in-sidebar recursive search ---- */
    async runSearch() {
        const q = this.search.query.trim();
        if (!q) {
            this.clearSearch();
            return;
        }

        this.search.active = true;
        this.search.running = true;
        this.search.error = "";

        try {
            const data = await simpleApiPost("/api/ext/coder/search", {
                sandbox: this.sandbox,
                query: q,
                regex: this.search.regex,
            });
            this.search.results = data.results || [];
            this.search.truncated = !!data.truncated;
        } catch (e) {
            this.search.results = [];
            this.search.error = this.errorText(e);
        } finally {
            this.search.running = false;
            this.search.done = true;
        }
    },

    clearSearch() {
        this.search.active = false;
        this.search.query = "";
        this.search.results = [];
        this.search.truncated = false;
        this.search.error = "";
        this.search.done = false;
    },

    openResult(r) {
        this.openFile({ path: r.file }, r.line);
    },

    /* ---- fuzzy quick-open (ctrl+p) ---- */
    async openQuickOpen(event) {
        // only act while the coder sidebar is actually visible; otherwise
        // leave the browser shortcut (print) alone
        const panel = document.querySelector(".coder-panel");
        if (!panel || !panel.offsetParent) return;

        if (event) event.preventDefault();

        if (!this.sandboxes.length) await this.loadSandboxes();
        if (!this.sandbox) return;

        if (this.quick.filesLoadedFor !== this.sandbox) {
            try {
                const data = await simpleApiFetch(`/api/ext/coder/files?sandbox=${encodeURIComponent(this.sandbox)}`);
                this.quick.files = data.files || [];
                this.quick.filesLoadedFor = this.sandbox;
            } catch (e) {
                this.quick.files = [];
            }
        }

        this.quick.query = "";
        this.quick.idx = 0;
        Alpine.store("ui").openModal("coder_quick");
    },

    quickMatches() {
        const q = (this.quick.query || "").trim().toLowerCase();
        const files = this.quick.files;

        if (!q) return files.slice(0, 40);

        const scored = [];
        for (const f of files) {
            const s = coderFuzzyScore(f.toLowerCase(), q);
            if (s > 0) scored.push([s, f]);
        }

        scored.sort((a, b) => b[0] - a[0]);
        return scored.slice(0, 40).map((x) => x[1]);
    },

    quickNav(delta) {
        const max = this.quickMatches().length - 1;
        this.quick.idx = Math.max(0, Math.min(this.quick.idx + delta, max));
    },

    quickEnter() {
        const f = this.quickMatches()[this.quick.idx];
        if (f) this.quickOpenFile(f);
    },

    quickOpenFile(path) {
        Alpine.store("ui").closeModal();
        this.openFile({ path });
    },

    closeQuick() {
        Alpine.store("ui").closeModal();
    },

    /* ---- drag & drop moving ---- */
    onDragStart(event, row) {
        if (this.read_only) {
            event.preventDefault();
            return;
        }

        this.dragPath = row.path;
        event.dataTransfer.setData("text/plain", row.path);
        event.dataTransfer.effectAllowed = "move";
    },

    onDragEnd() {
        this.dragPath = "";
        this.dropTarget = null;
    },

    // single dragover entry point for all rows: folders highlight as drop
    // targets; file rows accept drops too (meaning "move into the file's
    // parent folder"), and both stop propagation so the root highlight
    // doesn't fight with the row highlight
    onRowDragOver(event, row) {
        if (row.is_dir) {
            if (this.canDropInto(this.dragPath, row)) {
                event.preventDefault();
                event.stopPropagation();
                this.dropTarget = row.path;
            }
            return;
        }

        if (this.dragPath && this.dragPath !== row.path) {
            event.preventDefault();
            event.stopPropagation();
            this.dropTarget = null;
        }
    },

    canDropInto(src, targetRow) {
        if (!src || !targetRow || src === targetRow.path) return false;
        if (!targetRow.is_dir) return false;
        if (src.startsWith(targetRow.path + "/")) return false; // into itself
        const name = src.split("/").pop();
        if (targetRow.path + "/" + name === src) return false; // already there
        return true;
    },

    onFolderDrop(event, row) {
        event.preventDefault();
        event.stopPropagation();

        const src = this.dragPath;
        this.dropTarget = null;
        if (!this.canDropInto(src, row)) return;

        this.moveEntry(src, row.path + "/" + src.split("/").pop());
    },

    // dropping on a file row moves into that file's parent folder
    onFileDrop(event, row) {
        event.preventDefault();
        event.stopPropagation();
        this.dropTarget = null;

        const src = this.dragPath;
        const parent = row.path.split("/").slice(0, -1).join("/");
        const dst = (parent ? parent + "/" : "") + src.split("/").pop();
        if (src && dst !== src) this.moveEntry(src, dst);
    },

    onRootDragOver(event) {
        if (!this.dragPath) return;
        event.preventDefault();
        if (this.dragPath.includes("/")) this.dropTarget = "__root__";
    },

    onRootDrop(event) {
        event.preventDefault();
        this.dropTarget = null;

        const src = this.dragPath;
        if (!src || !src.includes("/")) return;

        this.moveEntry(src, src.split("/").pop());
    },

    async moveEntry(src, dst) {
        this.dragPath = "";
        if (!dst || src === dst) return;

        try {
            await simpleApiPost("/api/ext/coder/move", { sandbox: this.sandbox, src, dst });
            if (this.editor.path === src) this.editor.path = dst;
            await this.reloadAfterChange([
                src.split("/").slice(0, -1).join("/"),
                dst.split("/").slice(0, -1).join("/"),
            ]);
        } catch (e) {
            this.error = this.errorText(e);
        }
    },

    /* ---- extra context-menu actions ---- */
    copyPath(row) {
        const text = this.sandbox + "/" + row.path;
        if (navigator.clipboard) navigator.clipboard.writeText(text).catch(() => {});
    },

    async duplicateRow(row) {
        try {
            await simpleApiPost("/api/ext/coder/duplicate", { sandbox: this.sandbox, path: row.path });
            await this.reloadAfterChange([row.path.split("/").slice(0, -1).join("/")]);
        } catch (e) {
            this.error = this.errorText(e);
        }
    },

    // prefill (never auto-send) the chat input with a file reference
    askAI(row) {
        const chat = Alpine.store("chat");
        if (!chat) return;

        const line = `look at ${this.sandbox}/${row.path}: `;
        if (chat.user_input && chat.user_input.trim() &&
            !window.confirm("Replace the current chat input?")) {
            return;
        }

        chat.user_input = line;
    },

    errorText(e) {
        if (e && typeof e === "object") return e.message || JSON.stringify(e);
        return String(e);
    }
};

// -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
// tiny fuzzy scorer for quick-open: subsequence match with bonuses for
// consecutive runs and path-segment starts; shorter paths win ties.
function coderFuzzyScore(text, q) {
    let ti = 0;
    let score = 0;
    let run = 0;

    for (let qi = 0; qi < q.length; qi++) {
        const found = text.indexOf(q[qi], ti);
        if (found === -1) return 0;

        if (found === ti) {
            run++;
            score += 4 + run;
        } else {
            run = 0;
            score += 1;
        }

        if (found === 0 || text[found - 1] === "/") score += 6;
        ti = found + 1;
    }

    return score - Math.min(text.length, 60) / 60;
}

document.addEventListener("alpine:init", () => {
    Alpine.store("coderPanel", CODER_PANEL);
});

// -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
// fresh Proxy per mount (see shell.js shellTermComponent for why x-data
// must never receive the store object directly). the sidebar panel only
// mounts once today, but this keeps it remount-safe like git.js.
function coderPanelComponent() {
    const target = {};
    const src = () => Alpine.store("coderPanel") || CODER_PANEL;

    return new Proxy(target, {
        get(t, key) {
            if (key === Symbol.unscopables) return undefined;
            if (key in t) return t[key];
            const val = src()[key];
            return typeof val === "function" ? val.bind(src()) : val;
        },
        set(t, key, value) {
            if (key in t) {
                t[key] = value;
                return true;
            }
            src()[key] = value;
            return true;
        },
        has(t, key) {
            return key in t || key in src();
        },
        ownKeys() {
            return [...new Set([...Reflect.ownKeys(target), ...Object.keys(src())])];
        },
        getOwnPropertyDescriptor(t, key) {
            if (key in t) return Reflect.getOwnPropertyDescriptor(t, key);
            if (key in src()) {
                return { value: src()[key], enumerable: true, configurable: true, writable: true };
            }
            return undefined;
        },
    });
}
