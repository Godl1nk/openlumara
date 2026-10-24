SETTINGS_STORE = {
    // --- API State ---
    apiStatus: false,
    apiError: false,
    
    // --- Settings Data ---
    originalCategories: {},
    changedModuleSettings: new Set(),
    categories: {},

    activeCategory: null,
    loading: false,
    
    // --- Feature Flags ---
    showUnsafe: false,
    
    // --- Model Cache ---
    cachedModels: null,
    modelsLoadError: null,

    systemPrompt: '',
    
    // --- Computed Getters ---
    get hasChanges() {
        return JSON.stringify(this.categories) !== JSON.stringify(this.originalCategories);
    },

    get sortedCategories() {
        return Object.entries(this.categories)
            .sort(([a, catA], [b, catB]) => (catA.order || 0) - (catB.order || 0));
    },

    // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-12)
    // (the old flat `filteredSubItems` getter was replaced by groupedSubItems)
    // groups all (enabled + disabled) items of a module category by the category
    // each module/channel declares on its class. returns [{ label, items }] with
    // named categories sorted alphabetically and uncategorized items ("Other")
    // last. the label is empty when there is nothing to group by (single unnamed
    // group), so the templates can hide the header entirely in that case.
    get groupedSubItems() {
        return (cat, enabledOnly = false) => {
            const catData = this.categories[cat];
            if (!catData || !catData.enabled) return [];

            const moduleCategories = catData.moduleCategories || {};
            const pool = enabledOnly ? [...catData.enabled] : [...catData.enabled, ...catData.disabled];
            const visible = pool.filter(item =>
                this.showUnsafe || !(catData.unsafeModules || {})[item]
            );

            const groups = {};
            for (const item of visible) {
                const label = moduleCategories[item] || "Other";
                if (!groups[label]) groups[label] = [];
                groups[label].push(item);
            }

            const sorted = Object.entries(groups).sort(([a], [b]) => {
                if (a === "Other") return 1;
                if (b === "Other") return -1;
                return a.localeCompare(b);
            });

            const hideLabels = sorted.length === 1 && sorted[0][0] === "Other";
            return sorted.map(([label, items]) => ({
                label: hideLabels ? "" : label,
                items
            }));
        };
    },

    // --- Init & Load ---
    async init() {
        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
        // admin lockdown: the settings endpoints are blocked server-side,
        // so skip loading them entirely instead of erroring on 403s.
        if (window.ADMIN_SETTINGS_DISABLED) return;

        await this.load();
        await this.checkApiConnection();
    },

    async load() {
        this.loading = true;
        this.error = null;

        try {
            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
            // the backend now returns the fully merged, render-ready
            // category tree (schemas + values), so the client-side
            // structure builder and the module-info round-trip are gone.
            const payload = await simpleApiFetch('/api/settings/load');

            this.categories = payload.categories;
            this.originalCategories = JSON.parse(JSON.stringify(this.categories));
            this.changedModuleSettings.clear();

            this.showUnsafe = payload.show_unsafe_settings;

            this.systemPrompt = await simpleApiFetch("/api/chat/prompt");

            await this.checkApiConnection();
        } catch (err) {
            console.error('Failed to load settings:', err);
            this.error = err.message || 'Failed to load settings';
        } finally {
            this.loading = false;
        }
    },

    async checkApiConnection() {
        // get API connection status
        try {
            this.apiStatus = await simpleApiFetch("/api/check_connection");

            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-12)
            // once the api is reachable again, retire any stale model-load
            // error (e.g. from the earlier blur-detect on the api url
            // field). the "no models found" hint stays, since the list
            // itself is still empty until the user presses refresh.
            if (this.apiStatus) {
                this.modelsLoadError = null;
            }
        } catch (e) {
           this.apiStatus = false;
        }
    },

    async fetchModels() {
        console.log("fetching models..");

        this.loading = true;

        try {
            const res = await simpleApiFetch('/api/models');
            // the endpoint returns {models, current, image_model, ...}; keep the
            // store's cachedModels an array for every existing consumer
            this.cachedModels = Array.isArray(res?.models) ? res.models : [];
            this.modelsLoadError = null;
        } catch (err) {
            console.error('Failed to fetch models:', err);
            this.modelsLoadError = err || 'Failed to fetch models';
            this.cachedModels = null;
        }

        this.loading = false;
    },

    async saveSettings() {
        this.loading = true;
        this.error = null;

        console.log("saving settings to server..");

        try {
            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
            // send the (edited) category tree straight through; the
            // backend flattens it back into raw config itself, and now
            // also tells us whether the changes require a server restart
            // or an API reconnect (the client-side config diffing is gone)
            const result = await simpleApiPost('/api/settings/save', {
                categories: JSON.parse(JSON.stringify(this.categories)),
                changed_modules: Array.from(this.changedModuleSettings)
            });

            // restart server if enabled modules/channels changed
            if (result?.requires_restart) {
                console.log("restarting server..");
                this.originalCategories = JSON.parse(JSON.stringify(this.categories));
                this.changedModuleSettings.clear();

                await Alpine.store('system').restart("Restarting the server to apply your changes..");
                return;
            }

            // Reconnect API if API settings changed
            else if (result?.requires_reconnect) {
                try {
                    console.log("reconnecting API");
                    await simpleApiPost('/api/reconnect', {});
                    this.apiError = null;
                } catch (reconnectErr) {
                    this.apiError = reconnectErr;
                    console.warn('Reconnect failed:', reconnectErr);
                }
            }

            this.originalCategories = JSON.parse(JSON.stringify(this.categories));

            // re-fetch system prompt
            this.systemPrompt = await simpleApiFetch("/api/chat/prompt");

            // handle localstorage settings
            const ui = Alpine.store('ui');
            localStorage.setItem('expandReasoning', ui.expandReasoning);

            this.changedModuleSettings.clear();
        } catch (err) {
            this.error = err.message || 'Failed to save settings';
        } finally {
            this.loading = false;
        }
    },

    // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-12)
    // discard all pending edits: restore the category tree from the
    // snapshot taken at the last load/save and forget dirty modules.
    // used by the reset button in the settings modal footer.
    //
    // IMPORTANT: values are restored IN PLACE instead of swapping the
    // categories object. the field widgets capture their `setting` object
    // once (x-data="{ setting: ... }"), so a wholesale replacement leaves
    // every rendered input pointing at the old edited objects and the dom
    // never updates - reset appeared to do nothing. walking the existing
    // tree and writing the snapshot values back mutates the very objects
    // the dom is bound to, so every field snaps back.
    resetChanges() {
        const restore = (target, source) => {
            for (const key of Object.keys(target)) {
                if (!(key in source)) continue;
                const t = target[key];
                const s = source[key];
                const bothObj = t && s && typeof t === 'object' && typeof s === 'object';
                if (bothObj && !Array.isArray(t) && !Array.isArray(s)) {
                    restore(t, s);
                } else if (t !== s) {
                    // deep-copy so later edits never touch the snapshot
                    target[key] = (s && typeof s === 'object') ? JSON.parse(JSON.stringify(s)) : s;
                }
            }
        };
        restore(this.categories, this.originalCategories);

        this.changedModuleSettings.clear();
        this.error = null;
        this.apiError = null;
    },

    toggleEnabled(category, itemName) {
        const cat = this.categories[category];
        if (!cat) return;

        const isEnabled = cat.enabled.includes(itemName);
        
        if (isEnabled) {
            // Disable: remove from enabled, add to disabled
            cat.enabled = cat.enabled.filter(item => item !== itemName);
            cat.disabled.push(itemName);
        } else {
            // Enable: remove from disabled, add to enabled
            cat.disabled = cat.disabled.filter(item => item !== itemName);
            cat.enabled.push(itemName);
        }
        
        // Sort for consistency
        cat.enabled.sort();
        cat.disabled.sort();
    },

}
