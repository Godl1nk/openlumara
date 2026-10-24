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
    _tokStart: 0,
    _tokChars: 0,

    resetTokenRate() {
        this.tokens_per_second = 0;
        this._tokStart = 0;
        this._tokChars = 0;
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
