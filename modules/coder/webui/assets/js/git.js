/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
   git sidebar tab for the coder module: status, stage/unstage, commit,
   branch switching, log, and a diff viewer modal. talks to the
   /api/ext/coder/git_* routes. follows the sandbox selected in the coder
   sidebar when it can. */
const GIT_PANEL = {
    sandbox: "",
    subpath: "",
    repos: [],
    _autoPicked: false,
    read_only: false,
    ready: false,
    loading: false,
    error: "",
    is_repo: false,
    branch: "",
    branches: [],
    changes: [],
    message: "",
    committing: false,
    log: [],
    showLog: false,
    diff: { path: "", staged: false, lines: [], loading: false },

    async refresh(force = false) {
        const coder = Alpine.store("coderPanel");
        if (coder && coder.sandbox) {
            if (this.sandbox !== coder.sandbox) {
                // coder switched sandboxes: our repo selection is stale
                this.subpath = "";
                this.repos = [];
                this._autoPicked = false;
            }
            this.sandbox = coder.sandbox;
        } else if (!this.sandbox) {
            try {
                const data = await simpleApiFetch("/api/ext/coder/sandboxes") || {};
                this.sandbox = (data.sandboxes || [])[0] || "";
            } catch (e) {
                this.sandbox = "";
            }
        }

        if (!this.sandbox) {
            this.error = "no sandboxes configured";
            this.ready = true;
            return;
        }

        this.loading = true;
        this.error = "";

        // (re)discover repos inside the sandbox: the root itself plus nested
        // folders containing a .git, so 'dev/openlumara_dev' is selectable.
        // the header refresh button (refresh(true)) doubles as the rescan.
        if (!this.repos || !this.repos.length || force) {
            this._autoPicked = false;
            try {
                const rd = await simpleApiFetch(`/api/ext/coder/git_repos?sandbox=${encodeURIComponent(this.sandbox)}`);
                this.repos = rd.repos || [];
            } catch (e) {
                this.repos = [];
            }
        }

        if (!this.repos || !this.repos.includes(this.subpath)) {
            this.subpath = "";
        }

        try {
            const data = await simpleApiFetch(`/api/ext/coder/git_status?sandbox=${encodeURIComponent(this.sandbox)}&subpath=${encodeURIComponent(this.subpath)}`);
            this.is_repo = !!data.is_repo;

            // sandbox root isn't a repo but the scan found nested ones:
            // hop into the first one automatically, otherwise the panel
            // would sit on "not a repository" with a repo right next to it
            if (!this.is_repo && this.repos.length && !this._autoPicked) {
                this._autoPicked = true;
                this.subpath = this.repos.find(r => r !== "") || this.repos[0];
                return this.refresh();
            }

            this.branch = data.branch || "";
            this.branches = data.branches || [];
            this.changes = data.changes || [];
            this.read_only = !!data.read_only;
        } catch (e) {
            this.error = this.errorText(e);
            this.changes = [];
        } finally {
            this.loading = false;
            this.ready = true;
        }
    },

    stagedCount() {
        return this.changes.filter(c => c.staged).length;
    },

    badge(c) {
        if (c.untracked) return "new";
        if (c.staged) return "staged";
        return "changed";
    },

    async _gitPost(route, payload) {
        this.error = "";
        try {
            await simpleApiPost(`/api/ext/coder/${route}`, { sandbox: this.sandbox, subpath: this.subpath, ...payload });
            await this.refresh();
            return true;
        } catch (e) {
            this.error = this.errorText(e);
            return false;
        }
    },

    async switchRepo() {
        // subpath already bound via x-model. a manual choice wins from now
        // on: never auto-hop over the user's selection again
        this._autoPicked = true;
        await this.refresh();
    },



    repoLabel(repo) {
        if (!repo) return this.sandbox + " (root)";
        return this.sandbox + " / " + repo;
    },

    stage(path) { return this._gitPost("git_stage", { paths: [path] }); },
    unstage(path) { return this._gitPost("git_unstage", { paths: [path] }); },
    stageAll() { return this._gitPost("git_stage", { paths: this.changes.map(c => c.path) }); },
    unstageAll() { return this._gitPost("git_unstage", { paths: this.changes.map(c => c.path) }); },

    async commit() {
        const msg = (this.message || "").trim();
        if (!msg || this.committing) return;

        this.committing = true;
        this.error = "";

        try {
            await simpleApiPost("/api/ext/coder/git_commit", { sandbox: this.sandbox, message: msg });
            this.message = "";
            await this.refresh();
            if (this.showLog) await this.loadLog();
        } catch (e) {
            this.error = this.errorText(e);
        } finally {
            this.committing = false;
        }
    },

    async switchBranch(name) {
        if (!name || this.read_only) return;
        this.error = "";

        try {
            await simpleApiPost("/api/ext/coder/git_branch", { sandbox: this.sandbox, name });
        } catch (e) {
            this.error = this.errorText(e);
        }

        await this.refresh(true);
    },

    async toggleLog() {
        this.showLog = !this.showLog;
        if (this.showLog) await this.loadLog();
    },

    async loadLog() {
        try {
            const data = await simpleApiFetch(`/api/ext/coder/git_log?sandbox=${encodeURIComponent(this.sandbox)}&subpath=${encodeURIComponent(this.subpath)}`);
            this.log = data.log || [];
        } catch (e) {
            this.log = [];
        }
    },

    openDiff(c) {
        this.diff = { path: c.path, staged: c.staged, lines: ["loading.."], loading: true };
        Alpine.store("ui").openModal("git_diff");

        const params = `sandbox=${encodeURIComponent(this.sandbox)}&subpath=${encodeURIComponent(this.subpath)}` +
            `&path=${encodeURIComponent(c.path)}&staged=${c.staged ? 1 : 0}&untracked=${c.untracked ? 1 : 0}`;

        simpleApiFetch(`/api/ext/coder/git_diff?${params}`)
            .then(d => { this.diff.lines = String(d.diff || "(no changes)").split("\n"); })
            .catch(e => { this.diff.lines = [this.errorText(e)]; })
            .finally(() => { this.diff.loading = false; });
    },

    closeDiff() {
        Alpine.store("ui").closeModal();
    },

    errorText(e) {
        if (e && typeof e === "object") return e.message || JSON.stringify(e);
        return String(e);
    }
};

document.addEventListener("alpine:init", () => {
    Alpine.store("gitPanel", GIT_PANEL);
});

// -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
// fresh Proxy per mount (see shell.js shellTermComponent for why x-data
// must never receive the store object directly)
function gitPanelComponent() {
    const target = {};
    const src = () => Alpine.store("gitPanel") || GIT_PANEL;

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
