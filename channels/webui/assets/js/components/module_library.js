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
            const counts = { module: 0, channel: 0 };
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
                    items
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

                if (data.restart_required) this.restartNeeded = true;
                this.flash(action.charAt(0).toUpperCase() + action.slice(1) + ' complete.', 'success');
                await this.refresh();
            } catch (err) {
                this.flash(String(err), 'error');
            } finally {
                this.busyKey = null;
            }
        },

        install(m) {
            this.runAction(m, 'install');
        },

        update(m) {
            this.runAction(m, 'update');
        },

        async uninstall(m) {
            if (!confirm('Uninstall ' + m.name + '? Its settings are kept, but dependencies nothing else needs will be removed.')) return;
            this.runAction(m, 'uninstall');
        },

        async restart() {
            await Alpine.store('system').restart('Restarting the server to apply your module changes..');
        },
    };
}
