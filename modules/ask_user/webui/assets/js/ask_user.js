/*
 * Ask User Module - WebUI Controller
 * Connects to /api/ext/ask_user/ routes and renders a pending question as an
 * inline card above the chat input (no modal window).
 */

const ASK_USER_STORE = {
    current: null,
    textInput: "",
    submitting: false,
    error: "",
    _pollTimer: null,
    _countdownTimer: null,
    // absolute time the server-side question expires, in ms
    _deadline: null,

    init() {
        this.startPolling();
        // background tabs throttle timers, so resync the moment the tab returns
        document.addEventListener("visibilitychange", () => {
            if (!document.hidden) this.checkPending();
        });
    },

    startPolling() {
        clearInterval(this._pollTimer);
        // Poll every 2 seconds for pending AI questions
        this._pollTimer = setInterval(() => {
            this.checkPending();
        }, 2000);

        // Immediate check
        this.checkPending();
    },

    async checkPending() {
        try {
            const data = await simpleApiFetch("/api/ext/ask_user/pending");
            const pendingList = (data && data.pending) ? data.pending : [];

            if (pendingList.length > 0) {
                const target = pendingList[0];
                if (!this.current || this.current.id !== target.id) {
                    this.current = target;
                    this.textInput = "";
                    this.error = "";
                    this._deadline = Date.now() + (Number(target.remaining_seconds) || 0) * 1000;

                    // the card is bound to `current`, so no window to open
                    this.startCountdown();
                } else {
                    // Update remaining time and the deadline it is derived from
                    this.current.remaining_seconds = target.remaining_seconds;
                    this._deadline = Date.now() + (Number(target.remaining_seconds) || 0) * 1000;
                }
            } else if (this.current) {
                // No more pending questions
                this.current = null;
                this._deadline = null;
                this.stopCountdown();
            }
        } catch (e) {
            // Ignore background network/auth errors silently
        }
    },

    startCountdown() {
        clearInterval(this._countdownTimer);
        this._countdownTimer = setInterval(() => {
            if (!this.current) return;
            if (this._deadline == null) {
                this._deadline = Date.now() + (Number(this.current.remaining_seconds) || 0) * 1000;
            }
            // recompute from the wall clock: background tabs throttle this timer,
            // so decrementing a counter would drift past the server-side deadline
            const remaining = Math.max(0, Math.round((this._deadline - Date.now()) / 1000));
            this.current.remaining_seconds = remaining;
            if (remaining <= 0) {
                this.stopCountdown();
                this.checkPending();
            }
        }, 1000);
    },

    stopCountdown() {
        clearInterval(this._countdownTimer);
        this._countdownTimer = null;
    },

    async submitAnswer(answer) {
        if (!this.current) return;
        this.submitting = true;
        this.error = "";

        try {
            await simpleApiPost("/api/ext/ask_user/respond", {
                id: this.current.id,
                answer: String(answer).trim()
            });

            this.current = null;
            this._deadline = null;
            this.stopCountdown();
        } catch (err) {
            this.error = (typeof err === "string") ? err : (err.message || "Failed to submit response");
        } finally {
            this.submitting = false;
        }
    },

    async submitText() {
        if (!this.textInput || !this.textInput.trim()) return;
        await this.submitAnswer(this.textInput.trim());
    },

    async selectOption(opt) {
        await this.submitAnswer(opt);
    },

    async cancelCurrent() {
        if (!this.current) return;

        try {
            await simpleApiPost("/api/ext/ask_user/cancel", { id: this.current.id });
        } catch (e) {
            // Ignore cancel error
        }

        this.current = null;
        this._deadline = null;
        this.stopCountdown();
    }
};

document.addEventListener("alpine:init", () => {
    Alpine.store("askUser", ASK_USER_STORE);
    Alpine.store("askUser").init();
});
