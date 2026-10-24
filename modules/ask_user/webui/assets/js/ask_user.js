/*
 * Ask User Module - WebUI Controller
 * Connects to /api/ext/ask_user/ routes and provides interactive human-in-the-loop modal dialogs.
 */

const ASK_USER_STORE = {
    current: null,
    textInput: "",
    submitting: false,
    error: "",
    _pollTimer: null,
    _countdownTimer: null,

    init() {
        this.startPolling();
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

                    // Open the modal if not already open
                    if (Alpine.store("ui") && Alpine.store("ui").currentModal !== "ask_user") {
                        Alpine.store("ui").openModal("ask_user");
                    }
                    this.startCountdown();
                } else {
                    // Update remaining time
                    this.current.remaining_seconds = target.remaining_seconds;
                }
            } else if (this.current) {
                // No more pending questions
                this.current = null;
                this.stopCountdown();
                if (Alpine.store("ui") && Alpine.store("ui").currentModal === "ask_user") {
                    Alpine.store("ui").closeModal();
                }
            }
        } catch (e) {
            // Ignore background network/auth errors silently
        }
    },

    startCountdown() {
        clearInterval(this._countdownTimer);
        this._countdownTimer = setInterval(() => {
            if (this.current && this.current.remaining_seconds > 0) {
                this.current.remaining_seconds--;
            } else if (this.current && this.current.remaining_seconds <= 0) {
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
            this.stopCountdown();
            if (Alpine.store("ui")) {
                Alpine.store("ui").closeModal();
            }
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
        if (!this.current) {
            if (Alpine.store("ui")) Alpine.store("ui").closeModal();
            return;
        }

        try {
            await simpleApiPost("/api/ext/ask_user/cancel", { id: this.current.id });
        } catch (e) {
            // Ignore cancel error
        }

        this.current = null;
        this.stopCountdown();
        if (Alpine.store("ui")) {
            Alpine.store("ui").closeModal();
        }
    }
};

document.addEventListener("alpine:init", () => {
    Alpine.store("askUser", ASK_USER_STORE);
    Alpine.store("askUser").init();
});
