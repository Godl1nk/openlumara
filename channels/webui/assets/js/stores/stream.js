// -- AI GENERATED CODE (GPT-6) :: 2026-11-21 16:39:24 +08:00 harness:Codex
let STREAM_STORE = {
    state: 'idle',
    turn: [],
    processing: {},

    // nested agentchains (context compaction, foreground subagents) keyed by
    // stream id; each renders inline under the parent step that spawned it
    nestedChains: {},

    // children of a given parent lane attached to a given parent step
    // (attach_step 0 == spawned before the parent's first step, e.g. a
    // compaction that fired while processing the user message)
    nestedChildren(parentStreamId, attachStep) {
        if (parentStreamId == null) return [];
        return Object.values(this.nestedChains).filter(
            c => c.parent_id === parentStreamId && c.attach_step === attachStep
        );
    },

    // llama.cpp router model-load progress ({status, stage, percent}), null when idle
    modelLoad: null,

    // stores the final message after the stream has finished
    finalMessage: [],

    // messages sent while the current turn is still running
    queued: [],

    // -- AI GENERATED CODE (GPT-6.2-Sol) :: 2026-11-24 09:29 +08:00 harness:Codex
    tokens_per_second: null,

    resetTokenRate() {
        this.tokens_per_second = null;
    },

    applyServerTimings(timings) {
        const rate = timings?.predicted_per_second;
        if (Number.isFinite(rate) && rate > 0) this.tokens_per_second = rate;
    },

    async clear(preserveQueued = false) {
        if (typeof AudioManager !== 'undefined') AudioManager.stopProcessingSound();
        this.state = 'idle';
        this.turn = [];
        this.nestedChains = {};
        this.userMsg = null;
        this.processing = {};
        this.modelLoad = null;
        if (!preserveQueued) this.queued = [];
    }
}
