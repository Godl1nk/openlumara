/*
 * Multi-Provider API & Model Management Component
 * Controls the header quick switcher and the API settings page.
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
}

function syncManagedModelSetting(key, value) {
    const store = Alpine.store("settings");
    const field = store?.categories?.model?.settings?.[key];
    const original = store?.originalCategories?.model?.settings?.[key];
    if (field) field.value = value;
    if (original) original.value = value;
}


const MODEL_MANAGER_STORE = {
    providers: [],
    currentChatModel: "",
    imageModel: "dall-e-3",
    imageEditModel: "",
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
                this.imageEditModel = res.image_edit_model || "";
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
                if (m.enabled && !m.is_image) {
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
        effortSaving: false,

        get currentModel() {
            const store = Alpine.store("modelManager");
            return store?.currentChatModel || Alpine.store("settings")?.categories?.model?.settings?.name?.value || "";
        },

        get activeModelRef() {
            const current = this.currentModel;
            const store = Alpine.store("modelManager");
            for (const prov of (store?.providers || [])) {
                for (const m of (prov.models || [])) {
                    if (m.id === current) return { prov, model: m };
                }
            }
            return null;
        },

        get currentEffort() {
            const model = this.activeModelRef?.model;
            if (model) {
                return String(model.thinking_effort || "default").trim().toLowerCase() || "default";
            }

            const settings = Alpine.store("settings")?.categories?.model?.settings;
            const custom = String(settings?.custom_reasoning_effort?.value || "").trim();
            if (custom) return custom;

            const preset = String(settings?.reasoning_effort?.value || "").trim().toLowerCase();
            return preset && preset !== "none" ? preset : "default";
        },

        async setEffort(value) {
            if (!value || this.effortSaving) return;
            this.effortSaving = true;
            try {
                const ref = this.activeModelRef;
                if (ref) {
                    ref.model.thinking_effort = value;
                    await simpleApiPost("/api/provider/model/update", {
                        provider_id: ref.prov.id,
                        model_id: ref.model.id,
                        settings: { thinking_effort: value }
                    });
                } else {
                    // no provider entry (legacy single-endpoint setup): fall
                    // back to the global reasoning effort
                    const effort = value === "default" ? "none" : value;
                    await simpleApiPost("/api/model/effort/set", {
                        effort,
                        custom: ""
                    });
                    syncManagedModelSetting("reasoning_effort", effort);
                    syncManagedModelSetting("custom_reasoning_effort", "");
                }
            } catch (err) {
                alert("Failed to set reasoning effort: " + err);
            } finally {
                this.effortSaving = false;
            }
        },

        get enabledOptions() {
            const store = Alpine.store("modelManager");
            let list = store?.enabledModelsList || [];
            if (list.length === 0) {
                const cached = Alpine.store("settings")?.cachedModels;
                list = Array.isArray(cached) ? cached : [];
            }
            const current = this.currentModel;
            if (current && !list.includes(current)) {
                list = [current, ...list];
            }
            return list;
        },

        lazyFetch() {
            const store = Alpine.store("modelManager");
            if (!store) return;
            store.fetchProviders().then(() => {
                // legacy/seeded providers have no model list until refreshed;
                // fall back to the endpoint model list so the dropdown isn't empty
                if (!store.enabledModelsList.length) {
                    Alpine.store("settings")?.fetchModels?.();
                }
            });
        },

        async setModel(name) {
            if (!name || name === this.currentModel || this.saving) return;
            this.saving = true;
            try {
                const res = await simpleApiPost("/api/model/set", { name });
                const store = Alpine.store("modelManager");
                if (store) store.currentChatModel = name;
                syncManagedModelSetting("name", name);

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
        editingProviderId: null,
        searchTerms: {},
        collapsedMap: {},
        advancedModels: {},

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

        get imageEditModel() {
            return Alpine.store("modelManager")?.imageEditModel || "";
        },

        _modelKey(prov, model) {
            return prov.id + ":" + model.id;
        },

        isModelAdvancedOpen(prov, model) {
            return Boolean(this.advancedModels[this._modelKey(prov, model)]);
        },

        toggleModelAdvanced(prov, model) {
            const key = this._modelKey(prov, model);
            this.advancedModels[key] = !this.advancedModels[key];
        },

        modelAdvancedValue(model, key) {
            const value = model?.[key];
            return value === undefined || value === null || value === "" ? "default" : value;
        },

        modelAdvancedNumber(model, key) {
            const value = model?.[key];
            return value === undefined || value === null || value === "" || value === "default" ? "" : value;
        },

        modelDeveloperRoleValue(model) {
            const value = model?.use_developer_role;
            if (value === true || value === "true" || value === "on") return "on";
            if (value === false || value === "false" || value === "off") return "off";
            return "default";
        },

        modelCustomFieldsText(model) {
            const value = model?.custom_fields;
            if (!value || value === "default" || typeof value !== "object" || Array.isArray(value)) return "";
            return JSON.stringify(value, null, 2);
        },

        async updateModelAdvanced(prov, model, key, value, kind = "text", input = null) {
            const previous = model[key];
            let normalized = value;
            if (kind === "int") {
                if (value === "" || value === "default") {
                    normalized = "default";
                } else {
                    const parsed = Number(value);
                    if (!Number.isInteger(parsed) || parsed < 1) {
                        alert("Use a whole number greater than zero, or Default.");
                        if (input) input.value = this.modelAdvancedNumber(model, key);
                        return;
                    }
                    normalized = parsed;
                }
            } else if (kind === "developer") {
                normalized = value === "on" ? true : (value === "off" ? false : "default");
            }

            model[key] = normalized;
            try {
                await simpleApiPost("/api/provider/model/update", {
                    provider_id: prov.id,
                    model_id: model.id,
                    settings: { [key]: normalized }
                });
            } catch (e) {
                model[key] = previous;
                if (input) {
                    input.value = kind === "developer"
                        ? this.modelDeveloperRoleValue(model)
                        : this.modelAdvancedNumber(model, key);
                }
                alert("Failed to update advanced model settings: " + e);
            }
        },

        async updateModelCustomFields(prov, model, text, input) {
            const previous = model.custom_fields;
            let parsed = "default";
            if (text.trim()) {
                try {
                    parsed = JSON.parse(text);
                } catch {
                    parsed = null;
                }
                if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
                    alert("Custom request fields must be a JSON object, or left empty for Default.");
                    if (input) input.value = this.modelCustomFieldsText(model);
                    return;
                }
            }

            model.custom_fields = parsed;
            try {
                await simpleApiPost("/api/provider/model/update", {
                    provider_id: prov.id,
                    model_id: model.id,
                    settings: { custom_fields: parsed }
                });
            } catch (e) {
                model.custom_fields = previous;
                if (input) input.value = this.modelCustomFieldsText(model);
                alert("Failed to update custom request fields: " + e);
            }
        },

        _defaultModelOptions(imageCapable) {
            const options = [];
            const seen = new Set();
            for (const prov of this.providers) {
                if (prov.enabled === false) continue;
                for (const model of (prov.models || [])) {
                    if (!model.enabled || Boolean(model.is_image) !== imageCapable) continue;
                    if (seen.has(model.id)) continue;
                    seen.add(model.id);
                    options.push({ id: model.id, label: model.id });
                }
            }
            const current = imageCapable ? this.imageModel : this.currentChatModel;
            if (current && !seen.has(current)) {
                options.unshift({ id: current, label: current + " (current, unavailable)" });
            }
            return options;
        },

        get chatModelOptions() {
            return this._defaultModelOptions(false);
        },

        get imageModelOptions() {
            return this._defaultModelOptions(true);
        },

        get imageEditModelOptions() {
            const options = this.imageModelOptions.map(option => ({ ...option }));
            const current = this.imageEditModel;
            if (current && !options.some(option => option.id === current)) {
                options.unshift({ id: current, label: current + " (current, unavailable)" });
            }
            return options;
        },

        findManagedModel(modelId) {
            for (const prov of this.providers) {
                for (const model of (prov.models || [])) {
                    if (model.id === modelId) return model;
                }
            }
            return null;
        },

        async setDefaultChat(modelId) {
            const model = this.findManagedModel(modelId);
            if (!model) {
                alert("That model is no longer available. Refresh the provider and try again.");
                await Alpine.store("modelManager").fetchProviders();
                return;
            }
            if (model.id !== this.currentChatModel) {
                await this.setAsActiveChat(model);
            }
        },

        async setDefaultImageByName(modelId) {
            const model = this.findManagedModel(modelId);
            if (!model) {
                alert("That model is no longer available. Refresh the provider and try again.");
                await Alpine.store("modelManager").fetchProviders();
                return;
            }
            await this.setAsDefaultImage(model);
        },

        async setDefaultImageEdit(modelId) {
            if (!modelId) {
                try {
                    await simpleApiPost("/api/model/image/edit/set", { name: "" });
                    Alpine.store("modelManager").imageEditModel = "";
                    syncManagedModelSetting("image_edit_model", "");
                } catch (e) {
                    alert("Failed to use the generation model for image editing: " + e);
                }
                return;
            }
            const model = this.findManagedModel(modelId);
            if (!model) {
                alert("That model is no longer available. Refresh the provider and try again.");
                await Alpine.store("modelManager").fetchProviders();
                return;
            }
            if (!model.is_image || model.id === this.currentChatModel) {
                alert("Choose a marked, non-chat image model for image editing.");
                return;
            }
            try {
                await simpleApiPost("/api/model/image/edit/set", { name: model.id });
                Alpine.store("modelManager").imageEditModel = model.id;
                syncManagedModelSetting("image_edit_model", model.id);
            } catch (e) {
                alert("Failed to set the image editing model: " + e);
            }
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
                this.testResult = { success: false, error: (typeof e === "string" ? e : (e?.error || e?.message || "Connection failed")) };
            } finally {
                this.testing = false;
            }
        },

        beginEditProvider(prov) {
            this.editingProviderId = prov.id;
            this.formUrl = prov.url || "";
            this.formKey = prov.key || "";
            this.formFormat = prov.api_format || "auto";
            this.preset = "custom";
            this.testResult = null;
            this.formError = "";
        },

        cancelEditProvider() {
            this.editingProviderId = null;
            this.formUrl = "";
            this.formKey = "";
            this.formFormat = "auto";
            this.preset = "custom";
            this.testResult = null;
            this.formError = "";
        },

        async submitAddProvider() {
            if (!this.formUrl.trim()) return;
            this.adding = true;
            this.formError = "";
            try {
                if (this.editingProviderId) {
                    await simpleApiPost("/api/provider/update", {
                        id: this.editingProviderId,
                        updates: {
                            url: this.formUrl.trim(),
                            key: this.formKey.trim(),
                            api_format: this.formFormat
                        }
                    });
                    this.cancelEditProvider();
                } else {
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
                }
                await Alpine.store("modelManager").fetchProviders();
            } catch (e) {
                this.formError = typeof e === "string" ? e : (e?.error || e?.message || "Failed to save provider");
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
            const updates = (prov.models || []).map(m => {
                m.enabled = enabled;
                return simpleApiPost("/api/provider/model/update", {
                    provider_id: prov.id,
                    model_id: m.id,
                    settings: { enabled }
                }).catch(() => null);
            });
            await Promise.all(updates);
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

        async setAsActiveChat(model) {
            if (model.is_image) {
                alert("An image model cannot also be the default chat model.");
                return;
            }
            try {
                const res = await simpleApiPost("/api/model/set", { name: model.id });
                Alpine.store("modelManager").currentChatModel = model.id;
                syncManagedModelSetting("name", model.id);

                if (res && res.max_context) {
                    syncContextPill(res.max_context);
                }
            } catch (e) {
                alert("Failed to switch chat model: " + e);
            }
        },

        async toggleAsImageModel(prov, model) {
            if (model.is_image && (model.id === this.imageModel || model.id === this.imageEditModel)) {
                alert("Choose a different default image model before removing image capability.");
                return;
            }
            if (!model.is_image && model.id === this.currentChatModel) {
                alert("Choose a different default chat model first. A model cannot be used for both chat and images.");
                return;
            }
            const nextState = !model.is_image;
            model.is_image = nextState;
            try {
                await simpleApiPost("/api/provider/model/update", {
                    provider_id: prov.id,
                    model_id: model.id,
                    settings: { is_image: nextState }
                });
            } catch (e) {
                model.is_image = !nextState;
                alert("Failed to update image capability: " + e);
            }
        },

        async setAsDefaultImage(model) {
            if (!model.is_image || model.id === this.imageModel) return;
            if (model.id === this.currentChatModel) {
                alert("An image model cannot also be the default chat model.");
                return;
            }
            try {
                await simpleApiPost("/api/model/image/set", { name: model.id });
                Alpine.store("modelManager").imageModel = model.id;
                syncManagedModelSetting("image_model", model.id);
            } catch (e) {
                alert("Failed to set default image model: " + e);
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
                // the response carries the active model's context; only apply it
                // when the edited model is the one currently in use
                if (res && res.max_context && model.id === this.currentChatModel) {
                    syncContextPill(res.max_context);
                }
            } catch (e) {
                alert("Failed to update context length: " + e);
            }
        },

        async updateModelTemperature(prov, model, val) {
            const previous = model.temperature;
            model.temperature = val;
            try {
                await simpleApiPost("/api/provider/model/update", {
                    provider_id: prov.id,
                    model_id: model.id,
                    settings: { temperature: val }
                });
            } catch (e) {
                model.temperature = previous;
                alert("Failed to update temperature: " + e);
            }
        },

        async updateModelThinking(prov, model, val) {
            const previous = model.thinking_effort;
            model.thinking_effort = val;
            try {
                await simpleApiPost("/api/provider/model/update", {
                    provider_id: prov.id,
                    model_id: model.id,
                    settings: { thinking_effort: val }
                });
            } catch (e) {
                model.thinking_effort = previous;
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
            quality: "high"
        },
        providers: [],
        saving: false,
        pendingSave: false,
        error: "",

        async init() {
            try {
                const res = await simpleApiFetch("/api/ext/image_tools/settings");
                if (res) {
                    this.settings.enabled = res.enabled !== false;
                    this.settings.ask_before_generate = Boolean(res.ask_before_generate);
                    this.settings.endpoint = res.endpoint || "auto";
                    this.settings.quality = res.quality || "high";
                    this.providers = Array.isArray(res.providers) ? res.providers : [];
                    this.error = "";
                }
            } catch (e) {
                this.error = "Could not load image settings: " + (typeof e === "string" ? e : (e?.error || e?.message || "unknown error"));
                const mgr = Alpine.store("modelManager");
                if (mgr) {
                    this.providers = (mgr.providers || []).map(p => ({
                        id: p.id,
                        name: p.name,
                        enabled: p.enabled
                    }));
                }
            }
        },

        async save() {
            if (this.saving) {
                // coalesce rapid toggle/select changes instead of dropping them
                this.pendingSave = true;
                return;
            }
            this.saving = true;
            try {
                do {
                    this.pendingSave = false;
                    await simpleApiPost("/api/ext/image_tools/settings", {
                        enabled: this.settings.enabled,
                        ask_before_generate: this.settings.ask_before_generate,
                        endpoint: this.settings.endpoint,
                        quality: this.settings.quality
                    });
                    this.error = "";
                } while (this.pendingSave);
            } catch (e) {
                this.error = "Could not save image settings: " + (typeof e === "string" ? e : (e?.error || e?.message || "unknown error"));
            } finally {
                this.saving = false;
            }
        }
    };
}


document.addEventListener("alpine:init", () => {
    Alpine.store("modelManager", MODEL_MANAGER_STORE);
});
