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

    async clear() {
        this.turn = [];
        this.userMsg = null;
        this.processing = {};
        this.modelLoad = null;
    }
}
