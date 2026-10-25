// -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-12)
// Alpine component behind the settings modal's Module Library tab.
// Talks to the /api/libraries/* endpoints in channels/webui/channel.py,
// which proxy core.module_manager.ModuleManager.
function moduleLibrary() {
    return {
        modules: [],
        repos: [],
        loading: false,
        syncing: false,
        // key of the module currently being installed/updated/uninstalled
        // (null when idle). scalar on purpose: the bundled alpine build sets
        // the disabled attribute for non-boolean (undefined) bind values, so
        // all disabled bindings here must resolve to strict booleans.
        busyKey: null,
        message: null,
        messageKind: 'info',
        restartNeeded: false,

        // which of the two horizontal tabs (Modules | Channels) is open
        activeType: 'module',

        // completion notice shown inside the restart banner after an action
        restartNote: '',

        // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
        // pre-install code review: installing a module runs arbitrary Python
        // with full OpenLumara access, so install/update first open a
        // read-only source viewer (GET /api/libraries/source) with jump-links
        // to dependencies / on_install / on_ready and a two-step confirm.
        audit: null,
        auditLineHeight: 19,

        async init() {
            await this.refresh();
        },

        moduleKey(m) {
            return m.library + '/' + m.name;
        },

        // strict booleans for :disabled bindings (see busyKey note)
        anyBusy() {
            return this.busyKey !== null;
        },

        isBusy(m) {
            return this.busyKey === this.moduleKey(m);
        },

        // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-12)
        // per-type totals for the tab bar badges
        get typeCounts() {
            const counts = { module: 0, channel: 0, theme: 0, skill: 0 };
            for (const m of this.modules) {
                counts[m.type] = (counts[m.type] || 0) + 1;
            }
            return counts;
        },

        // maps a cloned library folder name back to its repo url, mirroring
        // ModuleManager.repo_name() so the group headers can show the url
        get libraryUrls() {
            const map = {};
            for (const url of this.repos) {
                let name = url.replace(/\/+$/, '').split('/').pop() || 'repo';
                if (name.endsWith('.git')) name = name.slice(0, -4);
                name = name.replace(/[^A-Za-z0-9._-]/g, '_');
                map[name] = url;
            }
            return map;
        },

        // items of the active type, grouped by the library they came from
        get groupedModules() {
            const groups = {};
            for (const m of this.modules) {
                if (m.type !== this.activeType) continue;
                if (!groups[m.library]) groups[m.library] = [];
                groups[m.library].push(m);
            }

            return Object.entries(groups)
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([library, items]) => ({
                    library,
                    url: this.libraryUrls[library] || library,
                    // installed first, then alphabetical
                    items: items.slice().sort((a, b) => {
                        if (a.installed !== b.installed) return a.installed ? -1 : 1;
                        return a.name.localeCompare(b.name);
                    })
                }));
        },

        flash(text, kind = 'info') {
            this.message = text;
            this.messageKind = kind;
        },

        async refresh() {
            this.loading = true;
            try {
                const data = await simpleApiFetch('/api/libraries/status');
                this.modules = data.modules || [];
                this.repos = data.repos || [];
            } catch (err) {
                this.flash(String(err), 'error');
            } finally {
                this.loading = false;
            }
        },

        async sync() {
            this.syncing = true;
            this.flash(null);
            try {
                const data = await simpleApiPost('/api/libraries/sync', {});
                this.modules = data.modules || [];
                if (data.synced) {
                    this.flash('Libraries synced.', 'success');
                } else {
                    this.flash('Sync finished, but no library could be reached - check the server logs.', 'error');
                }
            } catch (err) {
                this.flash(String(err), 'error');
            } finally {
                this.syncing = false;
            }
        },

        async runAction(m, action) {
            const key = this.moduleKey(m);
            this.busyKey = key;
            this.flash(null);

            try {
                const data = await simpleApiPost('/api/libraries/' + action, {
                    library: m.library,
                    name: m.name
                });

                const done = action.charAt(0).toUpperCase() + action.slice(1);
                if (data.restart_required) {
                    // one message instead of two: the restart banner carries
                    // the completion notice, so no separate success flash
                    this.restartNeeded = true;
                    this.restartNote = done + ' complete. Restart the server for it to take effect.';
                } else {
                    // themes/skills need no restart: carry the server's hint
                    // (e.g. '/skills reload', page refresh) in the flash
                    this.flash(done + ' complete. ' + (data.note || ''), 'success');
                }
                await this.refresh();
            } catch (err) {
                this.flash(String(err), 'error');
            } finally {
                this.busyKey = null;
            }
        },

        install(m) {
            this.openAudit(m, 'install');
        },

        update(m) {
            this.openAudit(m, 'update');
        },

        // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
        // code review modal logic (source viewing + flags + two-step confirm)
        async openAudit(m, mode) {
            this.audit = {
                m, mode,
                url: this.libraryUrls[m.library] || m.library,
                loading: true, error: null,
                code: '', files: [], file: '', truncated: false,
                flags: [], warnings: [], focusLine: 0
            };
            await this.fetchAuditSource();
        },

        async fetchAuditSource() {
            const a = this.audit;
            if (!a) return;
            a.loading = true;
            a.error = null;
            try {
                const url = '/api/libraries/source?library=' + encodeURIComponent(a.m.library)
                    + '&name=' + encodeURIComponent(a.m.name)
                    + (a.file ? '&file=' + encodeURIComponent(a.file) : '');
                const data = await simpleApiFetch(url);
                Object.assign(a, data, { loading: false });
            } catch (err) {
                a.error = String(err);
                a.loading = false;
            }
        },

        async auditSelectFile(rel) {
            if (!this.audit || rel === this.audit.file) return;
            this.audit.file = rel;
            this.audit.focusLine = 0;
            await this.fetchAuditSource();
        },

        get auditLineNums() {
            const count = this.audit && this.audit.code ? this.audit.code.split('\n').length : 0;
            return Array.from({ length: count }, (_, i) => i + 1);
        },

        get auditHighlighted() {
            if (!this.audit || !this.audit.code) return '';
            const code = this.audit.code;
            // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-24) harness:openlumara
            // pick the grammar by file extension: skills and themes review
            // .md/.json/.css files too, not just .py
            const LANG_BY_EXT = { py: 'python', json: 'json', css: 'css', md: 'markdown', yaml: 'yaml', yml: 'yaml', html: 'xml', js: 'javascript' };
            try {
                if (typeof hljs !== 'undefined') {
                    const ext = (this.audit.file || '').split('.').pop().toLowerCase();
                    const lang = LANG_BY_EXT[ext] || (this.audit.kind === 'skill' ? 'markdown' : 'python');
                    // hljs output is escaped markup, safe for x-html (same
                    // sanctioned escape hatch as the coder tool displays)
                    return hljs.getLanguage(lang)
                        ? hljs.highlight(code, { language: lang }).value
                        : hljs.highlightAuto(code).value;
                }
            } catch (err) { /* fall through to plain escaping */ }
            return escapeHtml(code);
        },

        auditJump(line) {
            if (!this.audit) return;
            this.audit.focusLine = line;
            const box = document.getElementById('library-audit-scroll');
            if (box) box.scrollTop = Math.max(0, (line - 1) * this.auditLineHeight - box.clientHeight / 3);
        },

        closeAudit() {
            this.audit = null;
        },

        // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-24) harness:openlumara
        // themes and skills are data, not executed code: the review dialog is
        // already a deliberate step, so no extra native confirm popup, no red
        // confirm button, and friendlier footer wording for them.
        get auditIsData() {
            return Boolean(this.audit) && (this.audit.m.type === 'theme' || this.audit.m.type === 'skill');
        },

        get auditConfirmLabel() {
            if (!this.audit) return 'Confirm';
            if (!this.auditIsData) return 'Confirm';
            return this.audit.mode === 'update' ? 'Update' : 'Install';
        },

        confirmAudit() {
            const a = this.audit;
            if (!a || a.loading || a.error) return;
            if (!this.auditIsData) {
                // modules and channels run with full access: two-step confirm
                const verb = a.mode === 'update' ? 'update' : 'install';
                const extra = a.warnings.length
                    ? '\n\nHeads up: this module uses shell/exec-style APIs (see the red warnings).'
                    : '';
                if (!confirm('Really ' + verb + ' "' + a.m.name + '"?\n\nInstalled code runs with full access to your host system - only continue if you trust this source.' + extra)) return;
            }
            const m = a.m;
            const action = a.mode;
            this.audit = null;
            this.runAction(m, action);
        },

        async uninstall(m) {
            const tail = m.type === 'theme'
                ? '? The theme files are removed from your user_webui_themes folder.'
                : m.type === 'skill'
                    ? '? The skill folder is removed from your skills folder.'
                    : '? Its settings are kept, but dependencies nothing else needs will be removed.';
            if (!confirm('Uninstall ' + m.name + tail)) return;
            this.runAction(m, 'uninstall');
        },

        async restart() {
            await Alpine.store('system').restart('Restarting the server to apply your module changes..');
        },
    };
}
