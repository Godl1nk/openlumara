/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
   git sidebar tab for the coder module: status, stage/unstage, commit,
   branch switching, log, and a diff viewer modal. talks to the
   /api/ext/coder/git_* routes. has its own sandbox picker: it does NOT
   follow the coder filetree tab. */
const GIT_PANEL = {
    sandboxes: [],
    sandbox: "",
    subpath: "",
    repos: [],
    _autoPicked: false,
    _didRestore: false,
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
    diff: { path: "", staged: false, lines: [], loading: false },
    push: {
        branch: "", remote: "", upstream: "", has_upstream: false, target: "",
        ahead: [], behind: 0, dirty: false, loading: false, pushing: false, error: "",
    },

    async refresh(force = false) {
        // own sandbox picker (header button forces a rescan of both the
        // sandbox list and the repos inside the selected sandbox)
        if (!this.sandboxes.length || force) {
            try {
                const sd = await simpleApiFetch("/api/ext/coder/sandboxes") || {};
                this.sandboxes = sd.sandboxes || [];
            } catch (e) {
                this.sandboxes = [];
            }
        }

        // selection vanished (sandbox removed from config): fall back
        if (this.sandbox && !this.sandboxes.includes(this.sandbox)) {
            this.sandbox = "";
            this.subpath = "";
            this.repos = [];
            this._autoPicked = false;
        }
        if (!this.sandbox && this.sandboxes.length) {
            // prefer the sandbox chosen before a page reload over the
            // plain first entry
            const saved = localStorage.getItem("git_sandbox") || "";
            this.sandbox = this.sandboxes.includes(saved) ? saved : this.sandboxes[0];
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

        // first load of the page only: restore the repo this sandbox had
        // before the reload (per-sandbox key, root = ""). once per page so
        // later refreshes never undo a manual pick of "(root)".
        if (!this.subpath && !this._didRestore) {
            this._didRestore = true;
            const savedRepo = localStorage.getItem("git_repo::" + this.sandbox) || "";
            if (this.repos.includes(savedRepo)) {
                this.subpath = savedRepo;
                this._autoPicked = true; // a restored choice beats auto-hop
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
            // remember the effective selection across page reloads
            this._save("git_sandbox", this.sandbox);
            this._save("git_repo::" + this.sandbox, this.subpath);
            this.loading = false;
            this.ready = true;
        }
    },

    _save(key, val) {
        try { localStorage.setItem(key, val); } catch (e) {}
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

    async switchSandbox() {
        // sandbox already bound via x-model. repos are per-sandbox: hop
        // straight back into whatever was last selected for this one
        // (refresh resets the subpath again if it no longer exists)
        this.subpath = localStorage.getItem("git_repo::" + this.sandbox) || "";
        this.repos = [];
        this._autoPicked = false;
        await this.refresh();
    },

    async switchRepo() {
        // subpath already bound via x-model. a manual choice wins from now
        // on: never auto-hop over the user's selection again
        this._autoPicked = true;
        await this.refresh();
    },

    repoLabel(repo) {
        // the sandbox has its own select above, so labels are relative
        if (!repo) return "(root)";
        return repo;
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
            await simpleApiPost("/api/ext/coder/git_commit", { sandbox: this.sandbox, subpath: this.subpath, message: msg });
            this.message = "";
            await this.refresh();
            // keep the log modal fresh if it happens to be open
            await this.loadLog();
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
            await simpleApiPost("/api/ext/coder/git_branch", { sandbox: this.sandbox, subpath: this.subpath, name });
        } catch (e) {
            this.error = this.errorText(e);
        }

        await this.refresh(true);
    },

    async openLog() {
        await this.loadLog();
        Alpine.store("ui").openModal("git_log");
    },

    closeLog() {
        Alpine.store("ui").closeModal();
    },

    async openPush() {
        // fetch exactly what would be pushed BEFORE showing the confirm
        // modal; errors (no remote, detached HEAD) go to the footer.
        if (this.push.loading || this.push.pushing) return;
        this.push.loading = true;
        this.push.error = "";

        try {
            const data = await simpleApiFetch(`/api/ext/coder/git_ahead?sandbox=${encodeURIComponent(this.sandbox)}&subpath=${encodeURIComponent(this.subpath)}`);
            const ahead = data.ahead || [];
            if (!ahead.length) {
                this.error = "nothing to push: every commit is already on the remote";
                return;
            }
            this.push = { ...this.push, ...data, ahead, loading: false, pushing: false, error: "" };
            Alpine.store("ui").openModal("git_push");
        } catch (e) {
            this.error = this.errorText(e);
        } finally {
            this.push.loading = false;
        }
    },

    closePush() {
        if (this.push.pushing) return; // never close mid-push
        Alpine.store("ui").closeModal();
    },

    async doPush() {
        if (this.push.pushing) return;
        this.push.pushing = true;
        this.push.error = "";

        try {
            await simpleApiPost("/api/ext/coder/git_push", { sandbox: this.sandbox, subpath: this.subpath });
            Alpine.store("ui").closeModal();
            await this.refresh();
        } catch (e) {
            // keep the modal open so the rejection reason is readable
            this.push.error = this.errorText(e);
        } finally {
            this.push.pushing = false;
        }
    },

    async loadLog() {
        try {
            // n=100: the backend default is only 20, which always fits the
            // modal body - so the list never got a scrollbar and deeper
            // history was unreachable. 100 is the backend's hard cap.
            const data = await simpleApiFetch(`/api/ext/coder/git_log?sandbox=${encodeURIComponent(this.sandbox)}&subpath=${encodeURIComponent(this.subpath)}&n=100`);
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
