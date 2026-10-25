let STREAM_STORE = {
    // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-12)
    // this is now a pure mirror of the backend's stream state, announced
    // over websocket as {type: "stream_state", state: "..."} on every
    // transition (and on connect). one of: idle, message_sending,
    // message_received, processing, thinking, streaming, calling_tools,
    // processing_tools. don't write to it from the frontend anymore.
    state: 'idle',

    // the live in-progress turn. starts as a bare [] and becomes a live
    // turn object {role, live, steps, final_messages} on the first
    // turn_step/turn_final event - EXACTLY the history turn shape, fed by
    // backend step upserts + final snapshots (core/turns.py step stream).
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
