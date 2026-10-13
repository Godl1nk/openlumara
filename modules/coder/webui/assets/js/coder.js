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
    "addon/lint/lint.css",
];

const CM_JS = [
    "lib/codemirror.js",
    "addon/comment/comment.js",
    "addon/dialog/dialog.js",
    "addon/search/searchcursor.js",
    "addon/search/search.js",
    "addon/search/match-highlighter.js",
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
    "addon/fold/markdown-fold.js",
    "addon/lint/lint.js",
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
    // tag pairing reads metadata the xml mode registers, so it goes last
    "addon/edit/matchtags.js",
];

// keymap/vim.js is ~100KB extra and only meaningful when the module
// setting says so, so it stays out of the main list and is fetched on
// demand (its presence is then cached by the browser like everything else)
function coderLoadVim() {
    if (window.CodeMirror && CodeMirror.Vim) return Promise.resolve();
    return coderLoadScript(CM_BASE + "keymap/vim.js");
}

// the live editor instance lives OUTSIDE the Alpine store on purpose:
// a reactive proxy wrapped around a whole CodeMirror would be a world
// of hurt, and nothing in the templates needs to read it.
let CODER_CM = null;
let CODER_CM_LOAD = null;

/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
   diff-point state (marks handed over by the git sidebar's diff view).
   CodeMirror line handles live OUTSIDE the Alpine store, same reasoning
   as CODER_CM: reactive proxies around editor internals are a bad time.
   spec = { adds: [1-based lines], dels: [...], label }; adds/dels hold the
   applied line handles; points holds the nav handles (sorted). */
let CODER_DIFF = { spec: null, adds: [], dels: [], points: [] };

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

// maximized is a persisted preference (localStorage, same pattern as
// coder_sandbox): once you go big, every later open stays big
function coderMaxStored() {
    try { return localStorage.getItem("coder_editor_maximized") === "1"; } catch (e) { return false; }
}

/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
   live lint: hands the buffer to the coder module's treesitter check
   (the same one that gates saves) and maps its diagnostics onto CM
   annotations. the lint addon debounces this; positions are clamped to
   the current document because typing between request and response can
   move the edges. */
// async getAnnotations signature per addon/lint/lint.js:
// (text, updateCallback, linterOptions, cm). in async mode the addon also
// drops responses when the doc changed while the request was in flight.
function coderLint(text, update, linterOptions, cm) {
    const panel = Alpine.store("coderPanel");
    if (!panel || !panel.editor.path) return update([]);

    simpleApiPost("/api/ext/coder/lint", {
        sandbox: panel.sandbox,
        path: panel.editor.path,
        content: text,
    }).then((data) => {
        const anns = (data && data.annotations) || [];
        update(anns.map((a) => coderLintAnnotation(cm, a)));
    }).catch(() => update([]));
}

function coderLintAnnotation(cm, a) {
    const lastLine = cm.lastLine();
    const line = Math.min(Math.max((a.line || 1) - 1, 0), lastLine);
    const ch = Math.min(Math.max((a.col || 1) - 1, 0), Math.max(0, cm.getLine(line).length - 1));

    let endLine = Math.min(Math.max((a.end_line || a.line || 1) - 1, 0), lastLine);
    let endCh = Math.max((a.end_col || (a.col || 1)) - 1, ch + 1);
    if (endCh > cm.getLine(endLine).length) {
        endLine = line;
        endCh = Math.max(cm.getLine(line).length, ch + 1);
    }

    return {
        from: CodeMirror.Pos(line, ch),
        to: CodeMirror.Pos(endLine, endCh),
        message: a.message || "syntax error",
        severity: "error",
    };
}

/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
   continue a line comment across newlines: "# foo" + Enter -> "# foo\n# ".
   the cursor must sit after a line-comment marker that the mode actually
   tokenises as a comment (so a "#" inside a string doesn't count). returns
   false when nothing applies and the caller should do a plain newline.
   block comments are left alone on purpose. */
function coderContinueLineComment(cm) {
    if (cm.getOption("readOnly")) return false;
    const mode = cm.getMode();
    const lc = mode && mode.lineComment;
    if (!lc) return false;

    const ranges = cm.listSelections();
    const replacements = [];
    for (const r of ranges) {
        if (!r.empty()) return false;
        const line = cm.getLine(r.head.line) || "";
        const idx = line.lastIndexOf(lc, r.head.ch - lc.length);
        if (idx === -1) return false;
        const type = String(cm.getTokenTypeAt({ line: r.head.line, ch: idx + 1 }));
        if (!/(^|\s)comment/.test(type)) return false;
        replacements.push("\n" + line.slice(0, idx) + lc + " ");
    }
    cm.replaceSelections(replacements, "end", "+");
    return true;
}

// ctrl+alt+g: prompt for a line number via the dialog addon
function coderJumpToLine(cm) {
    cm.openDialog('jump to line: <input type="text" style="width: 6em">', (val) => {
        const n = parseInt(val, 10);
        if (!n) return;

        const line = Math.min(Math.max(n - 1, 0), cm.lastLine());
        cm.setCursor({ line: line, ch: 0 });
        cm.scrollIntoView({ line: line, ch: 0 }, 120);
        cm.focus();
    }, {
        value: String(cm.getCursor().line + 1),
        selectValueOnOpen: true,
    });
}

function coderVimState(cm) {
    const vim = cm && cm.state && cm.state.vim;
    if (!vim) return { mode: "normal", subMode: "" };

    if (vim.visualMode) {
        return {
            mode: "visual",
            subMode: vim.visualLine ? "linewise" : vim.visualBlock ? "blockwise" : "",
        };
    }

    if (vim.insertMode) {
        return {
            mode: cm.getOption("overwrite") ? "replace" : "insert",
            subMode: "",
        };
    }

    return { mode: "normal", subMode: "" };
}

const CODER_PANEL = {
    sandboxes: [],
    sandbox: "",
    read_only: false,
    vim_mode: false, // mirrors the module setting (gated by enable_webui_extension)
    rows: [],
    expanded: {},
    children: {},
    rootEntries: null,
    loading: false,
    loaded: false,
    error: "",
    editor: { path: "", content: "", mode: "", dirty: false, saving: false, error: "", saved: "", cmReady: false, maximized: false, vimMode: "normal", vimSubMode: "" },
    caretLine: 1,
    caretCol: 1,
    selLen: 0,
    // diff points opened from the git sidebar (see CODER_DIFF above)
    diff: { active: false, count: 0, idx: -1, label: "" },
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
            this.vim_mode = !!data.vim_mode;
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

    // marks: optional { adds, dels, label } diff-point spec handed over by
    // the git sidebar's "edit" button (see git.js editFile)
    async openFile(row, line, marks) {
        const path = row.path;
        this.editor = { path: path, content: "", mode: "", dirty: false, saving: false, error: "", saved: "", cmReady: !!CODER_CM, maximized: coderMaxStored(), vimMode: "normal", vimSubMode: "" };
        this.clearDiffMarks();
        if (marks) CODER_DIFF.spec = marks;
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
            this.applyDiffMarks();
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
       diff points (git sidebar -> editor). added lines get a green
       background, deletion sites a red bar in a gutter that only exists
       while marks are active. everything keyed on LINE HANDLES, not line
       numbers, so the marks follow their line when edits shift the text
       above them. called from openFile (content just landed) and
       initEditor (editor just came up); both guard on the other half. */
    applyDiffMarks() {
        if (!CODER_CM || !CODER_DIFF.spec) return;
        // still fetching: same guard as revealPending
        if (!this.editor.content && !this.editor.error) return;

        const cm = CODER_CM;
        const spec = CODER_DIFF.spec;
        this.clearDiffMarks();
        CODER_DIFF.spec = spec; // clearDiffMarks wiped it; we're re-applying

        const last = cm.lastLine();
        const clamp = (n) => Math.max(0, Math.min(n - 1, last));

        for (const n of new Set(spec.adds.map(clamp))) {
            const h = cm.getLineHandle(n);
            cm.addLineClass(h, "background", "cm-diff-add");
            CODER_DIFF.adds.push(h);
        }

        if (spec.dels.length) {
            if (cm.getOption("gutters").indexOf("cm-diff-gutter") === -1) {
                cm.setOption("gutters", cm.getOption("gutters").concat("cm-diff-gutter"));
            }
            for (const n of new Set(spec.dels.map(clamp))) {
                const h = cm.getLineHandle(n);
                const el = document.createElement("div");
                el.className = "cm-diff-del-mark";
                el.title = "line(s) deleted here";
                cm.setGutterMarker(h, "cm-diff-gutter", el);
                CODER_DIFF.dels.push(h);
            }
        }

        // navigation points: every deletion site + the start of each
        // contiguous run of added lines, sorted
        const nums = new Set(spec.dels.map(clamp));
        let prev = -2;
        for (const n of [...new Set(spec.adds.map(clamp))].sort((a, b) => a - b)) {
            if (n !== prev + 1) nums.add(n);
            prev = n;
        }

        CODER_DIFF.points = [...nums].sort((a, b) => a - b).map((n) => cm.getLineHandle(n));
        this.diff = {
            active: CODER_DIFF.points.length > 0,
            count: CODER_DIFF.points.length,
            idx: -1,
            label: spec.label || "changes",
        };
    },

    clearDiffMarks() {
        this.diff = { active: false, count: 0, idx: -1, label: "" };

        const old = CODER_DIFF;
        CODER_DIFF = { spec: null, adds: [], dels: [], points: [] };

        if (!CODER_CM) return;
        for (const h of old.adds) {
            try { CODER_CM.removeLineClass(h, "background", "cm-diff-add"); } catch (e) {}
        }
        for (const h of old.dels) {
            try { CODER_CM.setGutterMarker(h, "cm-diff-gutter", null); } catch (e) {}
        }
        if (old.dels.length && CODER_CM.getOption("gutters").indexOf("cm-diff-gutter") !== -1) {
            CODER_CM.setOption("gutters", CODER_CM.getOption("gutters").filter((g) => g !== "cm-diff-gutter"));
        }
    },

    /* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
       cycle through the diff points (F8 / shift+F8 / header buttons).
       NOTE: CM5 line handles have NO live .line property - the number is
       computed by walking the line's parent tree, exposed as
       cm.getLineNumber(handle), which returns null once the line has been
       deleted. So resolve every handle through that API and skip the dead
       ones instead of reading handle.line. */
    diffJump(dir) {
        const cm = CODER_CM;
        const pts = CODER_DIFF.points;
        const n = pts ? pts.length : 0;
        if (!cm || !n) return;

        let idx = this.diff.idx;
        let line = null;
        for (let step = 0; step < n; step++) {
            idx += dir;
            if (idx >= n) idx = 0;
            else if (idx < 0) idx = n - 1;

            line = cm.getLineNumber(pts[idx]);
            if (line != null) break;
        }
        if (line == null) return; // every point's line is gone

        this.diff.idx = idx;
        const pos = { line: line, ch: 0 };
        cm.setCursor(pos);
        cm.scrollIntoView(pos, 120);
        cm.focus();
    },

    diffLabel() {
        const d = this.diff;
        if (!d.active) return "";
        return d.idx < 0 ? d.count + " " + d.label : (d.idx + 1) + " / " + d.count;
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
       mid-load); destroyEditor runs from the x-data destroy() hook Alpine
       calls on unmount.
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

        // vim keymap: fetched on demand when the module setting is on.
        // loaded BEFORE the editor exists so a mid-load modal close can
        // never strand a dead instance, and passed in as keyMap below.
        // (extraKeys still win over the vim keymap, so ctrl+s/f/h keep
        // working in normal mode)
        let vimOn = false;
        if (this.vim_mode) {
            try {
                await coderLoadVim();
                vimOn = !!CodeMirror.Vim;
            } catch (e) {}
            if (!host.isConnected) return;
            // if the vim addon failed to load, keep the UI honest: no vim
            // keymap means no vim mode line, and escape should close the modal.
            if (!vimOn) this.vim_mode = false;
        }

        const cm = CodeMirror(host, {
            value: this.editor.content,
            mode: this.editor.mode || null,
            theme: coderThemeName(),
            keyMap: vimOn ? "vim" : "default",
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
            gutters: ["CodeMirror-linenumbers", "CodeMirror-foldgutter", "CodeMirror-lint-markers"],
            // highlight every occurrence of the word under the caret (or
            // of the current selection). scrollbar annotation stays off:
            // the find addon already owns that lane
            highlightSelectionMatches: { showToken: /\w/, annotateScrollbar: false },
            matchTags: { bothTags: true },
            lint: { getAnnotations: coderLint, async: true, delay: 800, tooltips: true },
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
                "Ctrl-Alt-G": coderJumpToLine,
                "Cmd-Alt-G": coderJumpToLine,
                // jump between diff points when the file was opened from
                // the git sidebar's diff view (no-ops otherwise)
                "F8": () => this.diffJump(1),
                "Shift-F8": () => this.diffJump(-1),
                "Ctrl-/": "toggleComment",
                "Cmd-/": "toggleComment",
                // markdown keeps its lists going (that command falls back
                // to newlineAndIndent on its own outside lists); line
                // comments continue their prefix; everything else a plain
                // newline. CM5 has NO continue-comment command (that was
                // CM4), hence the hand-rolled helper below. must
                // execCommand directly: CM5 treats a function binding's
                // return value as "handled", not as a command.
                "Enter": (editor) => {
                    if (String(editor.getOption("mode")) === "markdown") {
                        editor.execCommand("newlineAndIndentContinueMarkdownList");
                    } else if (!coderContinueLineComment(editor)) {
                        editor.execCommand("newlineAndIndent");
                    }
                },
            },
        });

        CODER_CM = cm;
        this.editor.cmReady = true;

        if (vimOn) {
            const applyVimState = (event) => {
                const state = event && (event.mode || event.subMode !== undefined)
                    ? { mode: event.mode || "normal", subMode: event.subMode || "" }
                    : coderVimState(cm);
                this.editor.vimMode = state.mode;
                this.editor.vimSubMode = state.subMode;
            };

            applyVimState();

            // CodeMirror's custom vim-mode-change signal passes the event
            // object directly. Some CodeMirror event helpers pass (cm, event),
            // so accept both shapes.
            cm.on("vim-mode-change", (...args) => {
                applyVimState(args.length > 1 ? args[1] : args[0]);
            });
        }

        cm.on("change", () => {
            if (!this._silent && !this.editor.dirty) this.editor.dirty = true;
        });

        cm.on("cursorActivity", (c) => {
            const cur = c.getCursor();
            this.caretLine = cur.line + 1;
            this.caretCol = cur.ch + 1;
            this.selLen = c.somethingSelected() ? c.getSelection().length : 0;

            // fallback for vim mode: some mode transitions are easiest to
            // catch from the live vim state when the cursor/selection moves.
            if (vimOn) {
                const vimState = coderVimState(c);
                this.editor.vimMode = vimState.mode;
                this.editor.vimSubMode = vimState.subMode;
            }
        });

        // follow dark/light switches while the modal stays open
        const onTheme = () => cm.setOption("theme", coderThemeName());
        window.addEventListener("theme-changed", onTheme);
        cm._coderThemeOff = () => window.removeEventListener("theme-changed", onTheme);

        this.revealPending();
        this.applyDiffMarks();
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
        // CODER_CM is gone; this just drops the state + handle references
        this.clearDiffMarks();
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
                this.editor = { path: "", content: "", mode: "", dirty: false, saving: false, error: "", saved: "", cmReady: false, maximized: false, vimMode: "normal", vimSubMode: "" };
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

    vimModeLabel() {
        const mode = this.editor.vimMode || "normal";
        const sub = this.editor.vimSubMode || "";
        if (mode === "visual" && sub) {
            return "VISUAL " + sub.toUpperCase();
        }
        return mode.toUpperCase();
    },

    toggleMaximize() {
        this.editor.maximized = !this.editor.maximized;
        try { localStorage.setItem("coder_editor_maximized", this.editor.maximized ? "1" : "0"); } catch (e) {}

        // CodeMirror needs to recalculate its scroll/line layout after the
        // modal box changes size. Give the browser one paint to settle first.
        if (CODER_CM) {
            setTimeout(() => {
                if (CODER_CM) CODER_CM.refresh();
            }, 0);
        }
    },

    closeEditor() {
        if (this.editor.dirty && !window.confirm("This file has unsaved changes. Close anyway?")) {
            return;
        }

        this.clearDiffMarks();
        this.editor = { path: "", content: "", mode: "", dirty: false, saving: false, error: "", saved: "", cmReady: false, maximized: false, vimMode: "normal", vimSubMode: "" };
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
