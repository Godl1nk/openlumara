// -- AI GENERATED CODE (GPT-6) :: 2026-11-21 17:42:04 +08:00 harness:Codex
function thinkingToggle(initial) {
    return {
        saving: false,

        get globalEnabled() {
            return Alpine.store('modelManager').globalThinking ?? initial;
        },

        get enabled() {
            const ref = Alpine.store('modelManager').activeModelRef;
            const effort = String(ref?.model.thinking_effort || 'default').trim().toLowerCase();
            return effort === 'default' ? this.globalEnabled : effort !== 'none';
        },

        init() {
            const manager = Alpine.store('modelManager');
            if (!manager.loading && manager.globalThinking === null) manager.fetchProviders();
        },

        async toggle() {
            if (this.saving) return;
            this.saving = true;

            try {
                const manager = Alpine.store('modelManager');
                if (manager.globalThinking === null) {
                    await manager.fetchProviders();
                    if (manager.globalThinking === null) throw new Error('Model settings unavailable');
                }
                const next = !this.enabled;
                const ref = manager.activeModelRef;
                if (ref) {
                    const saved = ref.model.previous_thinking_effort || 'default';
                    const restored = saved === 'default' && !this.globalEnabled ? 'low' : saved;
                    const effort = next ? restored : 'none';
                    await manager.saveThinkingEffort(ref, effort);
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
