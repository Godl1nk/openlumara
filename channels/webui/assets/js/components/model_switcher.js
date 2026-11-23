// -- AI GENERATED CODE (GPT-6) :: 2026-11-21 17:42:04 +08:00 harness:Codex
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

function providerLabel(provider, providers) {
    const duplicate = providers.some(other => other.id !== provider.id && other.name === provider.name);
    return duplicate ? (provider.name || "Provider") + " · " + provider.id : provider.name || provider.id;
}

function syncManagedModelSetting(key, value) {
    const store = Alpine.store("settings");
    for (const tree of [store?.categories, store?.originalCategories]) {
        const field = tree?.model?.settings?.[key];
        if (field) field.value = value;
    }
}


const MODEL_MANAGER_STORE = {
    providers: [],
    currentChatModel: "",
    globalThinking: null,
    imageModel: "dall-e-3",
    currentProviderId: "",
    imageProviderId: "",
    disabledModels: [],
    selecting: false,
    loading: false,
    optionsError: false,
    modelOptionsRequest: null,

    async fetchProviders() {
        this.loading = true;
        try {
            const res = await simpleApiFetch("/api/providers");
            if (res) {
                this.providers = Array.isArray(res.providers) ? res.providers : [];
                this.currentChatModel = res.current_model || this.currentChatModel || "";
                this.globalThinking = res.enable_thinking ?? null;
                this.imageModel = res.image_model || this.imageModel || "dall-e-3";
                this.currentProviderId = res.provider_id || "";
                this.imageProviderId = res.image_provider_id || "";
                this.disabledModels = res.disabled_models || [];
            }
            return Boolean(res);
        } catch (e) {
            return false;
        } finally {
            this.loading = false;
        }
    },
    // -- AI GENERATED CODE (GPT-6.2-Sol) :: 2026-11-23 20:58 +08:00 harness:Codex
    loadModelOptions() {
        return this.modelOptionsRequest ??= this.fetchProviders().then(async loaded => {
            const settings = Alpine.store("settings");
            if (loaded && !this.hasCatalog) await settings.fetchModels();
            this.optionsError = !loaded || (!this.hasCatalog && Boolean(settings.modelsLoadError));
        }).finally(() => { this.modelOptionsRequest = null; });
    },

    selectedKey(image = false) {
        return JSON.stringify(image ? [this.imageProviderId, this.imageModel] : [this.currentProviderId, this.currentChatModel]);
    },

    get activeModelRef() {
        const prov = this.providers.find(provider => provider.enabled && provider.id === this.currentProviderId);
        const model = prov?.models.find(entry => entry.enabled && entry.id === this.currentChatModel);
        return model ? { prov, model } : null;
    },

    get hasCatalog() {
        return this.providers.some(provider => provider.models?.length) ||
            (this.providers.length > 0 && this.providers.every(provider => !provider.enabled));
    },

    modelOptions(image = false) {
        const options = [];
        // -- AI GENERATED CODE (GPT-6.2-Sol) :: 2026-11-21 21:34 +08:00 harness:Codex
        const add = (name, providerId = "", label = name) => {
            options.push({ name, providerId, label, key: JSON.stringify([providerId, name]), disabled: false });
        };
        if (this.hasCatalog) {
            const providers = this.providers.filter(provider => provider.enabled);
            for (const provider of providers) {
                const label = providers.length > 1 ? providerLabel(provider, providers) : "";
                for (const model of provider.models) {
                    if (model.enabled && Boolean(model.is_image) === image) {
                        add(model.id, provider.id, label ? model.id + " (" + label + ")" : model.id);
                    }
                }
            }
        } else if (!image) {
            const disabled = new Set(this.disabledModels.map(name => name.toLowerCase()));
            for (const name of Alpine.store("settings")?.cachedModels || []) {
                if (!disabled.has(name.toLowerCase())) add(name);
            }
        }
        const current = image ? this.imageModel : this.currentChatModel;
        const key = this.selectedKey(image);
        if (current && !options.some(option => option.key === key)) {
            options.unshift({ name: current, key, label: current + " (current)", disabled: true });
        }
        return options;
    },

    async selectModel(key, image = false) {
        if (this.selecting || key === this.selectedKey(image)) return;
        const option = this.modelOptions(image).find(item => item.key === key);
        if (!option || option.disabled) return;
        this.selecting = true;
        try {
            const result = await simpleApiPost(image ? "/api/model/image/set" : "/api/model/set", {
                name: option.name, provider_id: option.providerId
            });
            if (image) {
                this.imageModel = result.image_model;
                this.imageProviderId = result.provider_id || "";
                syncManagedModelSetting("image_model", this.imageModel);
                syncManagedModelSetting("image_provider_id", this.imageProviderId);
            } else {
                this.currentChatModel = result.name;
                this.currentProviderId = result.provider_id || "";
                syncManagedModelSetting("name", result.name);
                syncManagedModelSetting("provider_id", this.currentProviderId);
                syncContextPill(result.max_context);
                if (result.connection_error) alert("Model saved. Connection failed: " + result.connection_error);
            }
        } catch (error) {
            alert("Failed to select model: " + error);
        } finally {
            this.selecting = false;
        }
    },

    async saveThinkingEffort(ref, effort) {
        const result = await simpleApiPost("/api/provider/model/update", {
            provider_id: ref.prov.id,
            model_id: ref.model.id,
            settings: { thinking_effort: effort }
        });
        Object.assign(ref.model, result.model);
    }
};

function modelQuickSwitch() {
    return {
        effortSaving: false,

        get activeModelRef() {
            return Alpine.store("modelManager")?.activeModelRef;
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
                    await Alpine.store("modelManager").saveThinkingEffort(ref, value);
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
            return Alpine.store("modelManager").loadModelOptions();
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

        isSelected(prov, model, image = false) {
            const manager = Alpine.store("modelManager");
            return manager.selectedKey(image) === JSON.stringify([prov.id, model.id]);
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

        async toggleAsImageModel(prov, model) {
            if (model.is_image && this.isSelected(prov, model, true)) {
                alert("Choose a different default image model before removing image capability.");
                return;
            }
            if (!model.is_image && this.isSelected(prov, model)) {
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
                if (res && res.max_context && this.isSelected(prov, model)) {
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
            try {
                await Alpine.store("modelManager").saveThinkingEffort({ prov, model }, val);
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
            quality: "high"
        },
        providers: [],
        saving: false,
        pendingSave: false,
        error: "",

        async init() {
            try {
                const res = await simpleApiFetch("/api/ext/stable_diffusion/settings");
                if (res) {
                    this.settings.enabled = res.enabled !== false;
                    this.settings.selected_provider = Boolean(res.selected_provider);
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
                    await simpleApiPost("/api/ext/stable_diffusion/settings", {
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
