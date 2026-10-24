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

        // llama.cpp & some compatible servers attach native generation timings
        // (predicted_n tokens over predicted_ms); prefer those when present
        const timings = token.timings;
        if (timings && timings.predicted_n && timings.predicted_ms) {
            const rate = (Number(timings.predicted_n) * 1000) / Number(timings.predicted_ms);
            if (isFinite(rate) && rate > 0) {
                this.tokens_per_second = Math.round(rate);
                return;
            }
        }

        // fallback: rolling 2s window over streamed text (~4 chars per token)
        const text = token.content || "";
        const n = Math.max(1, Math.round(text.length / 4));
        const now = performance.now();
        this._tokSamples.push({ t: now, n });
        while (this._tokSamples.length && now - this._tokSamples[0].t > 2000) {
            this._tokSamples.shift();
        }
        const first = this._tokSamples[0];
        const span = (now - first.t) / 1000;
        if (span >= 0.6) {
            const total = this._tokSamples.reduce((sum, s) => sum + s.n, 0);
            this.tokens_per_second = Math.max(1, Math.round(total / span));
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
