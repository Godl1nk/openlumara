/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-13)
   memory sidebar panel logic. Plain global object consumed by
   x-data="MEMORY_PANEL" in sidebars/memories.html. Talks to the memory
   module's webui routes under /api/ext/memory/. */
const MEMORY_PANEL = {
    tab: "pinned",
    query: "",
    pinned: [],
    results: [],
    loadingPinned: false,
    loadingResults: false,
    loadedPinned: false,
    searchTimer: null,
    error: "",

    async refresh(force = false) {
        if (force || !this.loadedPinned) {
            await this.loadPinned();
        }
    },

    async loadPinned() {
        this.loadingPinned = true;
        this.error = "";

        try {
            this.pinned = await simpleApiFetch("/api/ext/memory/list_pinned") || [];
            this.loadedPinned = true;
        } catch (e) {
            this.error = this.errorText(e);
        } finally {
            this.loadingPinned = false;
        }
    },

    onSearchInput() {
        if (this.searchTimer) {
            clearTimeout(this.searchTimer);
        }

        if (this.query.trim().length < 2) {
            this.results = [];
            this.loadingResults = false;
            return;
        }

        this.searchTimer = setTimeout(() => this.runSearch(), 250);
    },

    async runSearch() {
        const q = this.query.trim();
        if (q.length < 2) {
            this.results = [];
            return;
        }

        this.loadingResults = true;
        this.error = "";

        try {
            const url = `/api/ext/memory/search?q=${encodeURIComponent(q)}&limit=30`;
            this.results = await simpleApiFetch(url) || [];
        } catch (e) {
            this.error = this.errorText(e);
            this.results = [];
        } finally {
            this.loadingResults = false;
        }
    },

    async togglePin(item) {
        const wasPinned = item.pinned;
        item.pinned = !wasPinned;
        this.error = "";

        try {
            const endpoint = wasPinned ? "unpin" : "pin";
            await simpleApiPost(`/api/ext/memory/${endpoint}`, { id: item.id });

            await this.loadPinned();

            if (this.tab === "search" && this.query.trim().length >= 2) {
                await this.runSearch();
            }
        } catch (e) {
            item.pinned = wasPinned;
            this.error = this.errorText(e);
        }
    },

    formatDate(value) {
        if (!value) {
            return "";
        }

        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return String(value);
        }

        return date.toLocaleDateString();
    },

    errorText(e) {
        if (e && typeof e === "object") {
            return e.message || JSON.stringify(e);
        }
        return String(e);
    }
};
