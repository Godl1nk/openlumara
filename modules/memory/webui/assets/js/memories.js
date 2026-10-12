/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-13)
   memory sidebar panel logic. The plain global object is registered as the
   Alpine store memoryPanel, shared by the sidebar and edit modal through
   memoryPanelComponent(). Talks to /api/ext/memory/. */
const MEMORY_PANEL = {
    tab: "pinned",
    query: "",
    tags: [],
    selectedTag: "",
    pinned: [],
    results: [],
    loadingPinned: false,
    loadingResults: false,
    loadedPinned: false,
    loadedTags: false,
    searchTimer: null,
    error: "",
    editing: null,
    editContent: "",
    editTags: "",
    savingEdit: false,

    async refresh(force = false) {
        if (!this.loadedTags) {
            await this.loadTags();
        }

        if (force || !this.loadedPinned) {
            await this.loadPinned();
        }

        if (this.tab === "search") {
            await this.runSearch();
        }
    },

    async loadPinned() {
        this.loadingPinned = true;
        this.error = "";

        try {
            const params = new URLSearchParams();
            if (this.selectedTag) {
                params.set("tag", this.selectedTag);
            }

            const url = "/api/ext/memory/list_pinned" + (params.toString() ? "?" + params.toString() : "");
            this.pinned = await simpleApiFetch(url) || [];
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

        this.searchTimer = setTimeout(async () => {
            await this.loadTags();
            await this.runSearch();
        }, 250);
    },

    async runSearch() {
        const q = this.query.trim();

        if (q.length < 2 && !this.selectedTag) {
            this.results = [];
            this.loadingResults = false;
            return;
        }

        this.loadingResults = true;
        this.error = "";

        try {
            if (q.length >= 2) {
                const params = new URLSearchParams({ q: q, limit: "30" });
                if (this.selectedTag) {
                    params.set("tag", this.selectedTag);
                }

                this.results = await simpleApiFetch(`/api/ext/memory/search?${params.toString()}`) || [];
            } else {
                const params = new URLSearchParams({ limit: "100" });
                if (this.selectedTag) {
                    params.set("tag", this.selectedTag);
                }

                this.results = await simpleApiFetch(`/api/ext/memory/list?${params.toString()}`) || [];
            }
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

            await this.loadTags();
            await this.loadPinned();

            if (this.tab === "search") {
                await this.runSearch();
            }
        } catch (e) {
            item.pinned = wasPinned;
            this.error = this.errorText(e);
        }
    },

    async loadTags() {
        try {
            const params = new URLSearchParams();
            params.set("tab", this.tab === "pinned" ? "pinned" : "search");

            const q = this.query.trim();
            if (this.tab === "search" && q.length >= 2) {
                params.set("q", q);
            }

            this.tags = await simpleApiFetch(`/api/ext/memory/tags?${params.toString()}`) || [];
            this.loadedTags = true;

            if (this.selectedTag && !this.tags.includes(this.selectedTag)) {
                this.selectedTag = "";
            }
        } catch (e) {
            this.tags = [];
            this.loadedTags = false;
        }
    },

    openEdit(item) {
        const tags = Array.isArray(item.tags) ? item.tags : [];
        this.editing = {
            id: item.id,
            content: item.content || "",
            tags: tags,
            pinned: !!item.pinned,
            date_created: item.date_created || "",
        };
        this.editContent = item.content || "";
        this.editTags = tags.join(", ");
        this.savingEdit = false;
        this.error = "";
        Alpine.store("ui").openModal("memory_edit");
    },

    closeEdit() {
        this.editing = null;
        this.editContent = "";
        this.editTags = "";
        this.savingEdit = false;
        this.error = "";
        Alpine.store("ui").closeModal();
    },

    async saveEdit() {
        if (!this.editing || this.savingEdit) {
            return;
        }

        const content = this.editContent.trim();
        if (!content) {
            this.error = "memory content cannot be empty";
            return;
        }

        const tags = this.editTags
            .split(",")
            .map(tag => tag.trim())
            .filter(tag => tag.length > 0);

        this.savingEdit = true;
        this.error = "";

        try {
            await simpleApiPost("/api/ext/memory/update", {
                id: this.editing.id,
                content: content,
                tags: tags
            });

            await this.loadTags();
            await this.loadPinned();

            if (this.tab === "search") {
                await this.runSearch();
            }

            this.closeEdit();
        } catch (e) {
            this.error = this.errorText(e);
        } finally {
            this.savingEdit = false;
        }
    },

    async onTabChange(tab) {
        this.tab = tab;

        await this.loadTags();

        if (tab === "pinned") {
            await this.loadPinned();
        } else {
            await this.runSearch();
        }
    },

    async onTagChange() {
        if (this.tab === "pinned") {
            await this.loadPinned();
        } else {
            await this.runSearch();
        }
    },

    async confirmDelete(item) {
        const message = "Are you sure you want to delete this memory?\n\nThis cannot be undone.";
        if (!window.confirm(message)) {
            return;
        }

        await this.deleteMemory(item);
    },

    async deleteMemory(item) {
        this.error = "";

        try {
            await simpleApiPost("/api/ext/memory/delete", { id: item.id });

            await this.loadTags();
            await this.loadPinned();

            if (this.tab === "search") {
                await this.runSearch();
            }
        } catch (e) {
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

document.addEventListener("alpine:init", () => {
    Alpine.store("memoryPanel", MEMORY_PANEL);
});

function memoryPanelComponent() {
    return Alpine.store("memoryPanel") || MEMORY_PANEL;
}
