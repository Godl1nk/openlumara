SYSTEM_STORE = {
    data: {},
    logs: [],
    running: true,
    restarting: false,
    message: '',

    update: {
        status: null,
        checking: false,
        updating: false,
        error: null,
        entries: [],
        checkedAt: null,

        get anyUpdates() {
            return Boolean(this.status && this.status.update_available)
                || (this.entries || []).some(e => e.update_available);
        },
    },

    autoCheckEnabled() {
        return localStorage.getItem('autoUpdateCheck') !== 'false';
    },

    async checkForUpdates() {
        if (this.update.checking || this.update.updating) return;
        this.update.checking = true;
        this.update.error = null;

        try {
            this.update.status = await simpleApiFetch("/api/system/update_check");
        } catch (e) {
            this.update.status = null;
            this.update.error = typeof e === 'string' ? e : 'Update check failed';
        }

        try {
            const fresh = await simpleApiFetch("/api/system/entry_updates");
            const oldErrors = {};
            for (const e of this.update.entries) {
                if (e.error) oldErrors[e.name] = e.error;
            }
            for (const e of fresh) {
                e.error = oldErrors[e.name] || null;
                e.updating = false;
            }
            this.update.entries = fresh;
            this.update.checkedAt = Date.now();
        } catch (e) {
            if (!this.update.entries.length) {
                this.update.entries = [{
                    name: 'modules & channels', type: 'module', library: '',
                    update_available: false, error: typeof e === 'string' ? e : 'Entry update check failed',
                }];
            }
        } finally {
            this.update.checking = false;
        }
    },

    async updateEntry(entry) {
        if (entry.updating || this.update.updating) return;

        entry.updating = true;
        entry.error = null;

        // -- AI GENERATED CODE (GPT-6.2-Sol) :: 2026-11-25 07:35 +08:00 harness:Codex
        let data;
        try {
            data = await simpleApiPost("/api/libraries/update", { name: entry.name });
        } catch (e) {
            entry.updating = false;
            entry.error = typeof e === 'string' ? e : 'Update failed';
            return;
        }

        if (data && data.restart_required) {
            this.restart("Restarting the server to load the updated " + data.kind + " '" + entry.name + "'");
            return;
        }

        entry.updating = false;

        try {
            const fresh = await simpleApiFetch("/api/system/entry_updates");
            this.update.entries = fresh;
            this.update.checkedAt = Date.now();
            const updated = fresh.find(x => x.name === entry.name);
            if (updated) Object.assign(entry, updated);
        } catch (e) {
        }
    },

    async performUpdate() {
        if (this.update.updating || this.update.entries.some(entry => entry.updating)) return;
        if (!confirm('Update OpenLumara now? The server will restart automatically when it finishes.')) return;

        await this.runUpdate("/api/system/update", "Updating OpenLumara…");
    },

    async updateAll() {
        if (!this.update.anyUpdates || this.update.updating || this.update.entries.some(entry => entry.updating)) return;
        if (!confirm('Update OpenLumara and all outdated modules/channels? The server will restart automatically when it finishes.')) return;

        const result = await this.runUpdate("/api/system/update_all", "Applying updates…");
        if (!result || result.restart_required) return;

        this.update.updating = false;
        this.restarting = false;
        await this.checkForUpdates();
        if (result.failed.length) this.update.error = result.failed.join(' | ');
    },

    async runUpdate(url, message) {
        this.update.error = null;
        this.update.updating = true;
        this.message = message;
        this.restarting = true;
        try {
            return await simpleApiPost(url);
        } catch (error) {
            if (typeof error === 'string' || window.socket?.readyState === WebSocket.OPEN) {
                this.update.updating = false;
                this.restarting = false;
                this.update.error = typeof error === 'string' ? error : 'Update failed';
            }
        }
    },

    async restart(message = 'Restarting server..') {
        this.message = message || "Restarting server..";
        this.restarting = true;

        try {
            await simpleApiPost("/api/system/restart");
        } catch (e) {
            // expected: the server dies while handling the request.
            // the websocket reconnect in services/websockets.js reloads
            // the page once the server is back, so keep the overlay up.
            if (window.socket && window.socket.readyState === WebSocket.OPEN) {
                // server survived the call: this was a real failure
                this.restarting = false;
                this.message = String(e);
            }
            return;
        }

        // request completed: the server is about to go down and the page
        // reloads itself on reconnect, so leave restarting=true here
    },

    async loadData() {
        // admin lockdown: logs are only shown in the (disabled) settings
        // modal and the endpoint is blocked, so skip them. /api/system/data
        // stays open since the context pill needs max_context from it.
        if (!window.ADMIN_SETTINGS_DISABLED) {
            // logs are best-effort: a refusal (403/401 for remote or
            // unauthenticated callers) must never break the load chain
            try {
                this.logs = await simpleApiFetch("/api/system/logs");
            } catch (e) {
                this.logs = [];
            }
        }
        this.data = await simpleApiFetch("/api/system/data");
    }
}
