const HUMANIZER_STORE = {
    draft: "",
    humanized: "",
    error: "",
    busy: false,
    copied: false,
    elapsed: 0,
    maxChars: 20000,
    _startedAt: 0,
    _timer: null,
    _copyTimer: null,

    get draftChars() {
        return this.draft.length;
    },

    get draftWords() {
        return this._countWords(this.draft);
    },

    get resultChars() {
        return this.humanized.length;
    },

    get resultWords() {
        return this._countWords(this.humanized);
    },

    get overLimit() {
        return this.maxChars > 0 && this.draftChars > this.maxChars;
    },

    get canRun() {
        return Boolean(this.draft.trim()) && !this.overLimit && !this.busy;
    },

    _countWords(text) {
        const value = String(text || "").trim();
        return value ? value.split(/\s+/).length : 0;
    },

    _formatError(error) {
        if (typeof error === "string") return error;
        if (error && typeof error === "object") {
            return error.error || error.message || error.detail || JSON.stringify(error);
        }
        return "Humanization failed.";
    },

    _beginTimer() {
        this._stopTimer();
        this._startedAt = Date.now();
        this.elapsed = 0;
        this._timer = setInterval(() => {
            this.elapsed = Math.max(0, Math.floor((Date.now() - this._startedAt) / 1000));
        }, 250);
    },

    _stopTimer() {
        if (this._timer !== null) {
            clearInterval(this._timer);
            this._timer = null;
        }
    },

    async run() {
        if (!this.canRun) return;

        this.busy = true;
        this.error = "";
        this.humanized = "";
        this.copied = false;
        this._beginTimer();

        try {
            const data = await simpleApiPost("/api/ext/humanizer/humanize", {
                draft: this.draft,
            });
            const output = typeof data === "string" ? data : data?.humanized;
            if (!output || !String(output).trim()) {
                throw "The Humanizer returned an empty result.";
            }
            this.humanized = String(output).trim();
        } catch (error) {
            this.error = this._formatError(error);
        } finally {
            this.busy = false;
            this._stopTimer();
        }
    },

    async paste() {
        try {
            const text = await navigator.clipboard.readText();
            if (!text) return;
            this.draft = text;
            this.error = "";
        } catch {
            this.error = "Clipboard access was denied. Paste directly into the draft field.";
        }
    },

    clear() {
        this.draft = "";
        this.humanized = "";
        this.error = "";
        this.copied = false;
        this.elapsed = 0;
    },

    useResult() {
        if (!this.humanized) return;
        this.draft = this.humanized;
        this.humanized = "";
        this.error = "";
        this.copied = false;
    },

    _legacyCopy(text) {
        const area = document.createElement("textarea");
        area.value = text;
        area.setAttribute("readonly", "");
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.appendChild(area);
        area.select();
        let ok = false;
        try {
            ok = document.execCommand("copy");
        } catch {
            ok = false;
        }
        document.body.removeChild(area);
        return ok;
    },

    async copy() {
        if (!this.humanized) return;
        let ok = false;
        try {
            await navigator.clipboard.writeText(this.humanized);
            ok = true;
        } catch {
            ok = this._legacyCopy(this.humanized);
        }
        if (!ok) {
            this.error = "Could not copy. Select the text manually instead.";
            return;
        }
        this.error = "";
        this.copied = true;
        if (this._copyTimer !== null) clearTimeout(this._copyTimer);
        this._copyTimer = setTimeout(() => {
            this.copied = false;
            this._copyTimer = null;
        }, 1600);
    },
};

const HUMANIZER_RAIL_ICON = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 20h9"/>
        <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>
        <path d="M15 5l4 4"/>
    </svg>`;

function mountHumanizerRailButton() {
    const tabbar = document.querySelector(".sidebar-tabbar");
    if (!tabbar || tabbar.querySelector(".humanizer-rail-btn")) return;

    const button = document.createElement("button");
    button.type = "button";
    button.className = "sidebar-tab ext humanizer-rail-btn";
    button.title = "Humanizer";
    button.setAttribute("aria-label", "Open Humanizer Studio");
    button.innerHTML = HUMANIZER_RAIL_ICON;
    button.addEventListener("click", () => {
        const stream = Alpine.store("stream");
        if (stream && stream.state !== "idle") return;
        Alpine.store("ui").openModal("humanizer");
        if (Alpine.store("ui").isMobile) {
            Alpine.store("ui").showSidebar = false;
        }
    });

    tabbar.appendChild(button);
    watchRailButton(button);
}

function watchRailButton(button) {
    if (!window.Alpine || !Alpine.store("stream") || button.dataset.streamBound) return;
    button.dataset.streamBound = "1";
    Alpine.effect(() => {
        const stream = Alpine.store("stream");
        button.disabled = Boolean(stream) && stream.state !== "idle";
    });
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountHumanizerRailButton);
} else {
    mountHumanizerRailButton();
}

document.addEventListener("alpine:init", () => {
    Alpine.store("humanizer", HUMANIZER_STORE);
});

document.addEventListener("alpine:initialized", () => {
    const button = document.querySelector(".humanizer-rail-btn");
    if (button) watchRailButton(button);
});
