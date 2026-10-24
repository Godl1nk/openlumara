let STREAM_STORE = {
    // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-12)
    // this is now a pure mirror of the backend's stream state, announced
    // over websocket as {type: "stream_state", state: "..."} on every
    // transition (and on connect). one of: idle, message_sending,
    // message_received, processing, thinking, streaming, calling_tools,
    // processing_tools. don't write to it from the frontend anymore.
    state: 'idle',

    // stores raw token data
    turn: [],
    processing: {},

    // llama.cpp router model-load progress ({status, stage, percent}), null when idle
    modelLoad: null,

    // stores the final message after the stream has finished
    finalMessage: [],

    // live generation speed (tokens/sec), estimated while streaming
    tokens_per_second: 0,
    _tokSamples: [],

    resetTokenRate() {
        this.tokens_per_second = 0;
        this._tokSamples = [];
    },

    recordToken(token) {
        if (!token) return;

        // servers batch several tokens per SSE chunk, so counting one token per
        // chunk under-reports by 3-4x; instead measure streamed text over a
        // rolling window and convert with ~4 chars per token
        const text = token.content || "";
        if (!text) return;

        const now = performance.now();
        this._tokSamples.push({ t: now, c: text.length });
        while (this._tokSamples.length > 2 && now - this._tokSamples[0].t > 2000) {
            this._tokSamples.shift();
        }
        const first = this._tokSamples[0];
        const span = (now - first.t) / 1000;
        if (span >= 0.8) {
            const chars = this._tokSamples.reduce((sum, s) => sum + s.c, 0);
            this.tokens_per_second = Math.max(1, Math.round((chars / 4) / span));
        }
    },

    async clear() {
        this.turn = [];
        this.userMsg = null;
        this.processing = {};
        this.modelLoad = null;
        this.resetTokenRate();
    }
}
