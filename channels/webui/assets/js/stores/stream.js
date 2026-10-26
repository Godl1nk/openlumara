let STREAM_STORE = {
    state: 'idle',
    turn: [],
    processing: {},

    // llama.cpp router model-load progress ({status, stage, percent}), null when idle
    modelLoad: null,

    // stores the final message after the stream has finished
    finalMessage: [],

    // live generation speed (tokens/sec), estimated while streaming
    tokens_per_second: 0,
    // "server" when the backend reported exact timings, "estimate" otherwise
    tokens_per_second_source: "",
    _tokStart: 0,
    _tokChars: 0,

    resetTokenRate() {
        // the readout is permanent: keep the last value and its source on
        // screen, only the measurement accumulators restart for the new turn
        this._tokStart = 0;
        this._tokChars = 0;
    },

    // llama.cpp & compatible servers attach exact generation timings
    // (predicted_n tokens over predicted_ms) to the final chunk
    applyServerTimings(timings) {
        if (!timings) return;
        const n = Number(timings.predicted_n);
        const ms = Number(timings.predicted_ms);
        if (!(n > 0) || !(ms > 0)) return;
        this.tokens_per_second = Math.max(1, Math.round((n * 1000) / ms));
        this.tokens_per_second_source = "server";
    },

    recordToken(token) {
        if (!token) return;

        // servers batch several tokens per SSE chunk, so counting one token per
        // chunk under-reports by 3-4x. Average the streamed text since the turn
        // started instead: a rolling window spikes to 2x on flushed batches
        const text = token.content || "";
        if (!text) return;

        const now = performance.now();
        if (!this._tokStart) this._tokStart = now;
        this._tokChars += text.length;

        // the first second is mostly latency jitter, so hold the value until then
        const span = (now - this._tokStart) / 1000;
        if (span >= 1) {
            this.tokens_per_second = Math.max(1, Math.round((this._tokChars / 4) / span));
            this.tokens_per_second_source = "estimate";
        }
    },

    async clear() {
        this.turn = [];
        this.userMsg = null;
        this.processing = {};
        this.modelLoad = null;
        // the last speed stays visible; a new turn replaces it once it has data
        this._tokStart = 0;
        this._tokChars = 0;
    }
}
