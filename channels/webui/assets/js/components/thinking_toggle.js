// -- AI GENERATED CODE (GPT-6) :: 2026-11-21 17:42:04 +08:00 harness:Codex
function thinkingToggle(initial) {
    return {
        saving: false,

        get globalEnabled() {
            return Alpine.store('modelManager').globalThinking ?? initial;
        },

        get enabled() {
            const ref = Alpine.store('modelManager').activeModelRef;
            const effort = modelOptionValue('thinking_effort', ref?.model.thinking_effort);
            return effort === 'default' ? this.globalEnabled : effort !== 'none';
        },

        // -- AI GENERATED CODE (GPT-6.2-Sol) :: 2026-11-23 21:59 +08:00 harness:Codex
        get busy() {
            const manager = Alpine.store('modelManager');
            const ref = manager.activeModelRef;
            return this.saving || manager.loading || manager.selecting ||
                Boolean(ref && manager.isSavingOption(ref.prov, ref.model, 'thinking_effort'));
        },

        init() {
            const manager = Alpine.store('modelManager');
            if (!manager.loading && manager.globalThinking === null) manager.fetchProviders();
        },

        async toggle() {
            // -- AI GENERATED CODE (GPT-6.2-Sol) :: 2026-11-23 20:58 +08:00 harness:Codex
            const manager = Alpine.store('modelManager');
            if (this.busy) return;
            this.saving = true;

            try {
                if (manager.globalThinking === null) {
                    await manager.fetchProviders();
                    if (manager.globalThinking === null) throw new Error('Model settings unavailable');
                }
                const next = !this.enabled;
                const ref = manager.activeModelRef;
                if (ref) {
                    let effort = 'none';
                    if (next) {
                        const saved = modelOptionValue('thinking_effort', ref.model.previous_thinking_effort);
                        const options = manager.modelOptionPresets(ref.model, 'thinking_effort');
                        effort = options.includes(saved) ? saved : 'default';
                        if (effort === 'default' && !this.globalEnabled) {
                            effort = options.includes('low') ? 'low' : options[0];
                            if (!effort) throw new Error('Add a thinking effort in model settings first.');
                        }
                    }
                    await manager.saveModelOption(ref, 'thinking_effort', effort);
                } else {
                    await simpleApiPost('/api/settings/field', { path: ['model', 'enable_thinking'], value: next });
                    manager.globalThinking = next;
                    syncManagedModelSetting('enable_thinking', next);
                }
            } catch (err) {
                alert('Failed to toggle thinking: ' + err);
            } finally {
                this.saving = false;
            }
        }
    };
}
