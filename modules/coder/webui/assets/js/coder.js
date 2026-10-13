/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
   coder sidebar (sandbox dropdown + lazy file tree) and file edit modal.
   Talks to /api/ext/coder/. the tree is kept flat (rows with depth) so
   alpine renders it with one x-for; children lazy-load on first expand. */
// -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
// fallback renderer for the highlight underlay when there is no hljs lang
// (plaintext, huge files, hljs unavailable): the textarea's own text is
// transparent, so the underlay must always show escaped source.
function coderEscapeHtml(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
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
    editor: { path: "", content: "", lang: "", dirty: false, saving: false, error: "", saved: "" },
    caretLine: 1,
    caretCol: 1,
    selLen: 0,
    _scrollTop: 0,

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
        this.editor = { path: row.path, content: "", lang: "", dirty: false, saving: false, error: "", saved: "" };
        this.caretLine = 1;
        this.caretCol = 1;
        this.selLen = 0;
        this._scrollTop = 0;
        Alpine.store("ui").openModal("coder_file");

        try {
            const data = await simpleApiFetch(`/api/ext/coder/read?sandbox=${encodeURIComponent(this.sandbox)}&path=${encodeURIComponent(row.path)}`);
            this.editor.content = data.content || "";
            this.editor.lang = this.detectLang(row.path, this.editor.content);

            if (line && line > 1) {
                this.revealLine(line);
            }
        } catch (e) {
            this.editor.error = this.errorText(e);
        }
    },

    // select + center a line after the editor mounts (search results, etc.)
    revealLine(line) {
        Alpine.nextTick(() => {
            const ta = document.querySelector(".coder-editor-modal .coder-textarea");
            if (!ta) return;

            const lines = this.editor.content.split("\n");
            let start = 0;
            for (let i = 0; i < line - 1 && i < lines.length; i++) {
                start += lines[i].length + 1;
            }

            const end = Math.min(start + (lines[line - 1] ? lines[line - 1].length : 0), this.editor.content.length);

            ta.focus();
            ta.setSelectionRange(start, end);

            const layout = this.ensureLayout();
            const row = layout && layout.offsets[line - 1] != null ? layout.offsets[line - 1] : line - 1;
            ta.scrollTop = Math.max(0, row * 20 - ta.clientHeight / 2);

            this.updateCaret(ta);
            this.syncHighlight({ target: ta });
        });
    },

    /* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
       syntax highlighting for the edit modal. language is resolved ONCE on
       open (extension map first, highlightAuto fallback for unknown ones)
       so per-keystroke re-highlights always take the cheap explicit-lang
       path. output feeds the pre>code.hljs underlay; the .hljs class means
       the core #code-theme link (github-dark/light, swapped by the theming
       store) colors it automatically. */
    detectLang(path, code) {
        const map = {
            py: "python", pyw: "python",
            js: "javascript", mjs: "javascript", cjs: "javascript",
            json: "json", jsonl: "json",
            html: "xml", htm: "xml", xml: "xml", svg: "xml", j2: "xml", jinja: "xml",
            css: "css", scss: "scss",
            toml: "ini", ini: "ini", cfg: "ini",
            yml: "yaml", yaml: "yaml",
            md: "markdown", markdown: "markdown",
            sh: "bash", bash: "bash", zsh: "bash",
            txt: "plaintext",
        };

        const ext = path.includes(".") ? path.split(".").pop().toLowerCase() : "";
        if (map[ext]) return map[ext];

        if (typeof hljs === "undefined" || !code) return "plaintext";

        try {
            const res = hljs.highlightAuto(code);
            return res.language && res.relevance >= 5 ? res.language : "plaintext";
        } catch (e) {
            return "plaintext";
        }
    },

    // simple memo: re-highlight only when lang or content actually changed
    _hlKey: "",
    _hlOut: "",

    highlighted() {
        const code = this.editor.content || "";
        const lang = this.editor.lang || "plaintext";
        const key = lang + "\0" + code;

        if (key === this._hlKey) return this._hlOut;

        let out;
        if (code.length > 300000 || lang === "plaintext" || typeof hljs === "undefined" || !hljs.getLanguage(lang)) {
            out = coderEscapeHtml(code);
        } else {
            try {
                out = hljs.highlight(code, { language: lang }).value;
            } catch (e) {
                out = coderEscapeHtml(code);
            }
        }

        // trailing newline: pre eats it, the textarea doesn't - without the
        // extra one the last line scrolls out of sync
        this._hlKey = key;
        this._hlOut = out + "\n";
        return this._hlOut;
    },

    syncHighlight(event) {
        const ta = event.target;
        const wrap = ta.closest(".coder-editor-wrap");
        if (!wrap) return;

        // cheap resize detector: re-measures the wrap layout only when the
        // textarea's content width actually changed (window/modal resize)
        if (this.layout && this.layout.width !== ta.clientWidth) {
            this.ensureLayout();
        }

        const pre = wrap.querySelector(".coder-hl");
        if (pre) {
            pre.scrollTop = ta.scrollTop;
            pre.scrollLeft = ta.scrollLeft;
        }

        const gutter = wrap.querySelector(".coder-gutter");
        if (gutter) gutter.scrollTop = ta.scrollTop;

        this._scrollTop = ta.scrollTop;
    },

    /* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
       line-number gutter + current-line band. both layers ride the same
       20px integer line-height as the text layers (fractional line-heights
       accumulate drift between the band and the textarea's real lines). */
    lineCount() {
        const c = this.editor.content || "";
        let n = 1;
        for (let i = 0; i < c.length; i++) {
            if (c.charCodeAt(i) === 10) n++;
        }
        return n;
    },

    /* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
       wrap-aware layout, vim-style: a wrapped logical line gets its number
       on the first visual row and BLANK rows for the continuations. since
       the textarea now soft-wraps, line N no longer sits at (N-1)*20px, so
       the gutter and the caret band need each line's real visual row count.
       measured with a hidden mirror div (same font/padding/width as the
       textarea) holding one div per logical line; heights are read in one
       batch. cached per content+width; recomputed at most once per
       keystroke, and only while the editor modal is open. */
    layout: null, // { key, width, rows: [{ n, visual }], offsets: [] }

    ensureLayout() {
        const ta = document.querySelector(".coder-editor-modal .coder-textarea");
        if (!ta) return this.layout;

        const content = this.editor.content || "";
        const width = ta.clientWidth;
        if (!width) return this.layout;

        const key = content;
        if (this.layout && this.layout.key === key && this.layout.width === width) {
            return this.layout;
        }

        let mirror = document.getElementById("coder-measure-mirror");
        if (!mirror) {
            mirror = document.createElement("div");
            mirror.id = "coder-measure-mirror";
            document.body.appendChild(mirror);
        }

        const cs = window.getComputedStyle(ta);
        mirror.style.position = "fixed";
        mirror.style.visibility = "hidden";
        mirror.style.top = "0";
        mirror.style.left = "-9999px";
        mirror.style.boxSizing = "border-box";
        mirror.style.width = width + "px";
        mirror.style.padding = cs.padding;
        mirror.style.font = cs.font;
        mirror.style.fontFamily = cs.fontFamily;
        mirror.style.fontSize = cs.fontSize;
        mirror.style.lineHeight = "20px";
        mirror.style.letterSpacing = cs.letterSpacing;
        mirror.style.tabSize = cs.tabSize;
        mirror.style.whiteSpace = "pre-wrap";
        mirror.style.overflowWrap = "break-word";
        mirror.style.wordBreak = "normal";

        const lines = content.split("\n");
        mirror.textContent = "";

        const frag = document.createDocumentFragment();
        const divs = [];
        for (const line of lines) {
            const d = document.createElement("div");
            d.style.lineHeight = "20px";
            // empty divs measure 0px in a pre-wrap mirror; give them a row
            d.textContent = line === "" ? "\u200b" : line;
            divs.push(d);
            frag.appendChild(d);
        }
        mirror.appendChild(frag);

        // one forced reflow, then all heights are available
        const rows = [];
        const offsets = [];
        let acc = 0;
        for (let i = 0; i < divs.length; i++) {
            const visual = Math.max(1, Math.round(divs[i].offsetHeight / 20));
            rows.push({ n: i + 1, visual: visual });
            offsets.push(acc);
            acc += visual;
        }

        this.layout = { key, width, rows, offsets };
        this.layoutTick++;
        return this.layout;
    },

    // bumped whenever the measured layout changes, so templates that read
    // gutterCells() re-render after the first (post-mount) measurement
    layoutTick: 0,

    // flattened gutter CELLS: number on the first visual row of each
    // logical line, blank cells for wrapped continuations (vim style).
    // flattened here rather than in the template: an x-for collection
    // expression can't reference its own index (Alpine evaluates it
    // before (cell, i) exist), so ids are precomputed.
    gutterCells() {
        this.layoutTick; // reactive dep: repaint when a new layout lands

        // first render can happen before the textarea exists (Alpine walks
        // top-down): fall back to 1 row per line so numbers show at once,
        // corrected into place as soon as ensureLayout() can measure
        const layout = this.ensureLayout();
        const rows = layout && layout.rows.length
            ? layout.rows
            : Array.from({ length: this.lineCount() }, (_, i) => ({ n: i + 1, visual: 1 }));

        const cells = [];
        for (const r of rows) {
            for (let k = 0; k < r.visual; k++) {
                cells.push({ id: r.n + "-" + k, n: k === 0 ? r.n : "" });
            }
        }
        return cells;
    },

    gutterVars() {
        const count = this.lineCount();
        if (count > 5000) return "--coder-gutter-w: 0px";
        const digits = Math.max(2, String(count).length);
        return `--coder-gutter-w: ${digits * 9 + 24}px`;
    },

    updateCaret(el) {
        if (!el || typeof el.selectionStart !== "number") return;

        const sel = el.selectionStart;
        const before = el.value.slice(0, sel);
        let n = 1;
        let lastNl = -1;
        for (let i = 0; i < before.length; i++) {
            if (before.charCodeAt(i) === 10) {
                n++;
                lastNl = i;
            }
        }

        this.caretLine = n;
        this.caretCol = sel - lastNl;
        this.selLen = Math.abs((el.selectionEnd || sel) - sel);
    },

    activeLineStyle() {
        const layout = this.ensureLayout();
        if (!layout || !layout.rows.length) return "opacity: 0";

        // offset in visual rows (wrap-aware), then to pixels
        const row = layout.offsets[this.caretLine - 1] || 0;
        return `transform: translateY(${row * 20 - this._scrollTop + 12}px)`;
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
                this.editor = { path: "", content: "", lang: "", dirty: false, saving: false, error: "", saved: "" };
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

    insertTab(event) {
        const el = event.target;
        const start = el.selectionStart;
        const end = el.selectionEnd;

        this.editor.content = this.editor.content.substring(0, start) + "    " + this.editor.content.substring(end);
        this.editor.dirty = true;

        Alpine.nextTick(() => {
            el.selectionStart = el.selectionEnd = start + 4;
        });
    },

    async save() {
        if (this.editor.saving || this.read_only) return;

        this.editor.saving = true;
        this.editor.error = "";

        try {
            await simpleApiPost("/api/ext/coder/save", {
                sandbox: this.sandbox,
                path: this.editor.path,
                content: this.editor.content,
            });

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

        this.editor = { path: "", content: "", lang: "", dirty: false, saving: false, error: "", saved: "" };
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
