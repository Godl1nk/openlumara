/*
 * Multi-Provider API & Model Management Component
 * Controls the Header Quick Switcher and the Model Providers Management Modal.
 */

const PRESET_URLS = {
    custom: "",
    openai: "https://api.openai.com/v1",
    openrouter: "https://openrouter.ai/api/v1",
    deepseek: "https://api.deepseek.com/v1",
    ollama: "http://localhost:11434/v1",
    llamacpp: "http://localhost:8080/v1",
    groq: "https://api.groq.com/openai/v1",
    together: "https://api.together.xyz/v1",
    mistral: "https://api.mistral.ai/v1"
};
function syncContextPill(maxContext) {
    if (maxContext && Alpine.store("system") && Alpine.store("system").data) {
        Alpine.store("system").data.max_context = Number(maxContext);
    }
    if (Alpine.store("chat") && typeof Alpine.store("chat").loadContextSize === "function") {
        Alpine.store("chat").loadContextSize();
    }
}


const MODEL_MANAGER_STORE = {
    providers: [],
    currentChatModel: "",
    imageModel: "dall-e-3",
    loading: false,
    _pollTimer: null,

    async fetchProviders() {
        this.loading = true;
        try {
            const res = await simpleApiFetch("/api/providers");
            if (res) {
                this.providers = Array.isArray(res.providers) ? res.providers : [];
                this.currentChatModel = res.current_model || this.currentChatModel || "";
                this.imageModel = res.image_model || this.imageModel || "dall-e-3";
            }
        } catch (e) {
            // Ignore background network/auth errors silently
        } finally {
            this.loading = false;
        }
    },

    get enabledModelsList() {
        const models = [];
        for (const prov of this.providers) {
            if (!prov.enabled) continue;
            for (const m of (prov.models || [])) {
                if (m.enabled) {
                    models.push(m.id);
                }
            }
        }
        return models;
    }
};

function modelQuickSwitch() {
    return {
        saving: false,

        get currentModel() {
            const store = Alpine.store("modelManager");
            return store?.currentChatModel || Alpine.store("settings")?.categories?.model?.settings?.name?.value || "";
        },

        get enabledOptions() {
            const store = Alpine.store("modelManager");
            let list = store?.enabledModelsList || [];
            if (list.length === 0) {
                list = Alpine.store("settings")?.cachedModels || [];
            }
            const current = this.currentModel;
            if (current && !list.includes(current)) {
                list = [current, ...list];
            }
            return list;
        },

        lazyFetch() {
            const store = Alpine.store("modelManager");
            if (store) store.fetchProviders();
        },

        async setModel(name) {
            if (!name || name === this.currentModel || this.saving) return;
            this.saving = true;
            try {
                const res = await simpleApiPost("/api/model/set", { name });
                const store = Alpine.store("modelManager");
                if (store) store.currentChatModel = name;

                const field = Alpine.store("settings")?.categories?.model?.settings?.name;
                if (field) field.value = name;

                if (res && res.max_context) {
                    syncContextPill(res.max_context);
                }
            } catch (err) {
                alert("Failed to switch model: " + err);
            } finally {
                this.saving = false;
            }
        }
    };
}

function providerManagerComponent() {
    return {
        preset: "custom",
        formUrl: "",
        formKey: "",
        formFormat: "auto",
        testing: false,
        testResult: null,
        adding: false,
        formError: "",
        searchTerms: {},
        collapsedMap: {},

        init() {
            const store = Alpine.store("modelManager");
            if (store) {
                store.fetchProviders();
            }
        },

        get providers() {
            return Alpine.store("modelManager")?.providers || [];
        },

        get providersLoading() {
            return Alpine.store("modelManager")?.loading || false;
        },

        get currentChatModel() {
            return Alpine.store("modelManager")?.currentChatModel || "";
        },

        get imageModel() {
            return Alpine.store("modelManager")?.imageModel || "";
        },

        applyPreset() {
            const url = PRESET_URLS[this.preset];
            if (url) {
                this.formUrl = url;
            }
        },

        async testCurrentEndpoint() {
            if (!this.formUrl.trim()) return;
            this.testing = true;
            this.testResult = null;
            try {
                const res = await simpleApiPost("/api/provider/test", {
                    url: this.formUrl.trim(),
                    key: this.formKey.trim()
                });
                this.testResult = res;
            } catch (e) {
                this.testResult = { success: false, error: (typeof e === "string" ? e : (e.message || "Connection failed")) };
            } finally {
                this.testing = false;
            }
        },

        async submitAddProvider() {
            if (!this.formUrl.trim()) return;
            this.adding = true;
            this.formError = "";
            try {
                await simpleApiPost("/api/provider/add", {
                    url: this.formUrl.trim(),
                    key: this.formKey.trim(),
                    name: this.preset !== "custom" ? this.preset.toUpperCase() : "",
                    type: "llm",
                    api_format: this.formFormat
                });
                // Reset form
                this.formUrl = "";
                this.formKey = "";
                this.preset = "custom";
                this.testResult = null;
                await Alpine.store("modelManager").fetchProviders();
            } catch (e) {
                this.formError = typeof e === "string" ? e : "Failed to add provider";
            } finally {
                this.adding = false;
            }
        },

        formatProviderName(prov) {
            if (!prov || !prov.name) return "Provider";
            if (prov.name === "API_URL_HERE") {
                return "Default Endpoint (Setup needed)";
            }
            return prov.name;
        },

        getProviderTypeBadge(prov) {
            const url = (prov.url || "").toLowerCase();
            if (url.includes("localhost") || url.includes("127.0.0.1") || url.includes("docker.internal")) {
                return "LOCAL";
            }
            if (url.includes("openrouter") || url.includes("swap") || url.includes("litellm")) {
                return "PROXY";
            }
            return "CLOUD";
        },

        maskKey(k) {
            if (!k) return "";
            if (k.length <= 8) return "••••";
            return k.substring(0, 4) + "..." + k.substring(k.length - 4);
        },

        enabledModelCount(prov) {
            return (prov.models || []).filter(m => m.enabled).length;
        },

        isCollapsed(pid) {
            return Boolean(this.collapsedMap[pid]);
        },

        toggleCollapse(pid) {
            this.collapsedMap[pid] = !this.collapsedMap[pid];
        },

        filteredModels(prov) {
            const list = prov.models || [];
            const term = (this.searchTerms[prov.id] || "").toLowerCase().trim();
            if (!term) return list;
            return list.filter(m => (m.id || "").toLowerCase().includes(term));
        },

        async toggleProviderEnabled(prov) {
            try {
                await simpleApiPost("/api/provider/update", {
                    id: prov.id,
                    updates: { enabled: !prov.enabled }
                });
                prov.enabled = !prov.enabled;
            } catch (e) {
                alert("Failed to toggle provider: " + e);
            }
        },

        async toggleImageProvider(prov) {
            try {
                const nextState = !prov.is_image_provider;
                await simpleApiPost("/api/provider/update", {
                    id: prov.id,
                    updates: { is_image_provider: nextState }
                });
                prov.is_image_provider = nextState;
            } catch (e) {
                alert("Failed to mark image provider: " + e);
            }
        },

        async removeProvider(prov) {
            if (!confirm(`Delete provider "${prov.name}" and remove all its models?`)) return;
            try {
                await simpleApiPost("/api/provider/delete", { id: prov.id });
                await Alpine.store("modelManager").fetchProviders();
            } catch (e) {
                alert("Failed to delete provider: " + e);
            }
        },

        async refreshProvider(prov) {
            try {
                await simpleApiPost("/api/provider/refresh", { id: prov.id });
                await Alpine.store("modelManager").fetchProviders();
            } catch (e) {
                alert("Failed to refresh models: " + e);
            }
        },

        async setAllModels(prov, enabled) {
            for (const m of (prov.models || [])) {
                m.enabled = enabled;
                simpleApiPost("/api/provider/model/update", {
                    provider_id: prov.id,
                    model_id: m.id,
                    settings: { enabled }
                }).catch(() => {});
            }
        },

        async toggleModelActive(prov, model) {
            const nextState = !model.enabled;
            model.enabled = nextState;
            try {
                await simpleApiPost("/api/provider/model/update", {
                    provider_id: prov.id,
                    model_id: model.id,
                    settings: { enabled: nextState }
                });
            } catch (e) {
                model.enabled = !nextState;
                alert("Failed to update model: " + e);
            }
        },

        async setAsActiveChat(modelId) {
            try {
                const res = await simpleApiPost("/api/model/set", { name: modelId });
                Alpine.store("modelManager").currentChatModel = modelId;
                const field = Alpine.store("settings")?.categories?.model?.settings?.name;
                if (field) field.value = modelId;

                if (res && res.max_context) {
                    syncContextPill(res.max_context);
                }
            } catch (e) {
                alert("Failed to switch chat model: " + e);
            }
        },

        async toggleAsImageModel(prov, model) {
            try {
                await simpleApiPost("/api/model/image/set", { name: model.id });
                Alpine.store("modelManager").imageModel = model.id;

                await simpleApiPost("/api/provider/model/update", {
                    provider_id: prov.id,
                    model_id: model.id,
                    settings: { is_image: true }
                });
            } catch (e) {
                alert("Failed to set image model: " + e);
            }
        },

        async updateModelContext(prov, model, val) {
            model.context_length = val;
            try {
                const res = await simpleApiPost("/api/provider/model/update", {
                    provider_id: prov.id,
                    model_id: model.id,
                    settings: { context_length: val }
                });
                if (res && res.max_context) {
                    syncContextPill(res.max_context);
                }
            } catch (e) {
                alert("Failed to update context length: " + e);
            }
        },

        async detectContext(prov, model) {
            try {
                const res = await simpleApiPost("/api/provider/detect_context", {
                    model_id: model.id
                });
                if (res && res.context_length) {
                    model.context_length = String(res.context_length);
                    const upd = await simpleApiPost("/api/provider/model/update", {
                        provider_id: prov.id,
                        model_id: model.id,
                        settings: { context_length: model.context_length }
                    });
                    if (upd && upd.max_context) {
                        syncContextPill(upd.max_context);
                    }
                }
            } catch (e) {
                alert("Failed to detect context: " + e);
            }
        },

        async updateModelThinking(prov, model, val) {
            model.thinking_effort = val;
            try {
                await simpleApiPost("/api/provider/model/update", {
                    provider_id: prov.id,
                    model_id: model.id,
                    settings: { thinking_effort: val }
                });
            } catch (e) {
                alert("Failed to update thinking effort: " + e);
            }
        }
    };
}
function imageGenSettingsComponent() {
    return {
        settings: {
            enabled: true,
            ask_before_generate: false,
            endpoint: "auto",
            model: "Qwen-Image-2.1",
            quality: "high",
            edit_endpoint: "auto",
            edit_model: "same"
        },
        providers: [],
        saving: false,

        async init() {
            try {
                const res = await simpleApiFetch("/api/ext/image_tools/settings");
                if (res) {
                    this.settings.enabled = res.enabled !== false;
                    this.settings.ask_before_generate = Boolean(res.ask_before_generate);
                    this.settings.endpoint = res.endpoint || "auto";
                    this.settings.model = res.model || "Qwen-Image-2.1";
                    this.settings.quality = res.quality || "high";
                    this.settings.edit_endpoint = res.edit_endpoint || "auto";
                    this.settings.edit_model = res.edit_model || "same";
                    this.providers = Array.isArray(res.providers) ? res.providers : [];
                }
            } catch (e) {
                const mgr = Alpine.store("modelManager");
                if (mgr) {
                    this.providers = (mgr.providers || []).map(p => ({
                        id: p.id,
                        name: p.name,
                        models: (p.models || []).map(m => m.id || String(m))
                    }));
                }
            }
        },

        get availableModels() {
            const models = new Set();
            for (const p of this.providers) {
                if (this.settings.endpoint !== "auto" && p.name !== this.settings.endpoint) continue;
                for (const m of (p.models || [])) {
                    models.add(m);
                }
            }
            return Array.from(models);
        },

        async save() {
            if (this.saving) return;
            this.saving = true;
            try {
                await simpleApiPost("/api/ext/image_tools/settings", this.settings);
                const mgr = Alpine.store("modelManager");
                if (mgr && this.settings.model) {
                    mgr.imageModel = this.settings.model;
                }
            } catch (e) {
                // Ignore silent save error
            } finally {
                this.saving = false;
            }
        }
    };
}


document.addEventListener("alpine:init", () => {
    Alpine.store("modelManager", MODEL_MANAGER_STORE);
});
