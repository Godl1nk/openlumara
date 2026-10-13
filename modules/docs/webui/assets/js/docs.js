/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
   docs sidebar browser + viewer modal logic. Talks to /api/ext/docs/.
   the tree is kept flat (rows with a depth) so alpine can render it with
   a single x-for; children are lazy-loaded on first expand and cached. */
const DOCS_PANEL = {
    folders: [],
    folder: "",
    rows: [],
    expanded: {},
    children: {},
    rootEntries: null,
    loading: false,
    loaded: false,
    error: "",
    viewer: { open: false, folder: "", path: "", html: "", error: "" },

    async refresh(force = false) {
        if (!this.folders.length || force) {
            await this.loadFolders();
        }

        if (this.folder && (force || !this.loaded)) {
            await this.loadRoot();
        }
    },

    async loadFolders() {
        try {
            this.folders = await simpleApiFetch("/api/ext/docs/folders") || [];
        } catch (e) {
            this.folders = [];
        }

        if (!this.folder && this.folders.length) {
            this.folder = this.folders[0];
        }
    },

    async onFolderChange() {
        this.expanded = {};
        this.children = {};
        this.rootEntries = null;
        this.rows = [];
        this.loaded = false;

        if (this.folder) {
            await this.loadRoot();
        }
    },

    async loadRoot() {
        this.loading = true;
        this.error = "";

        try {
            const data = await simpleApiFetch(`/api/ext/docs/list?folder=${encodeURIComponent(this.folder)}&subfolder=`);
            this.rootEntries = this.toEntries(data);
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

    toEntries(data) {
        const nameOf = (p) => p.split("/").filter(Boolean).pop() || p;

        const dirs = (data.subfolders || []).map(p => ({ path: p, name: nameOf(p), dir: true }));
        const files = (data.files || []).map(p => ({ path: p, name: nameOf(p), dir: false }));

        return dirs.concat(files);
    },

    rebuild() {
        const out = [];

        const walk = (entries, depth) => {
            for (const entry of entries) {
                out.push({ path: entry.path, name: entry.name, dir: entry.dir, depth: depth });

                if (entry.dir && this.expanded[entry.path] && this.children[entry.path]) {
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
                const data = await simpleApiFetch(`/api/ext/docs/list?folder=${encodeURIComponent(this.folder)}&subfolder=${encodeURIComponent(row.path)}`);
                this.children[row.path] = this.toEntries(data);
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

    async openFile(row) {
        this.viewer = { open: true, folder: this.folder, path: row.path, html: "", error: "" };
        Alpine.store("ui").openModal("doc_viewer");

        try {
            const data = await simpleApiFetch(`/api/ext/docs/read?folder=${encodeURIComponent(this.folder)}&path=${encodeURIComponent(row.path)}`);
            this.viewer.html = this.render(data.content || "");
        } catch (e) {
            this.viewer.error = this.errorText(e);
        }
    },

    render(content) {
        // marked + DOMPurify ship with the core webui; fall back to a
        // <pre> if either is absent
        if (typeof marked !== "undefined" && marked.parse && typeof DOMPurify !== "undefined") {
            try {
                return DOMPurify.sanitize(marked.parse(content));
            } catch (e) { /* fall through */ }
        }

        const escaped = content
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");
        return `<pre class="docs-plain">${escaped}</pre>`;
    },

    closeViewer() {
        this.viewer = { open: false, folder: "", path: "", html: "", error: "" };
        Alpine.store("ui").closeModal();
    },

    errorText(e) {
        if (e && typeof e === "object") return e.message || JSON.stringify(e);
        return String(e);
    }
};

document.addEventListener("alpine:init", () => {
    Alpine.store("docsPanel", DOCS_PANEL);
});

// -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
// fresh Proxy per mount (see shell.js shellTermComponent for why x-data
// must never receive the store object directly)
function docsPanelComponent() {
    const target = {};
    const src = () => Alpine.store("docsPanel") || DOCS_PANEL;

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
