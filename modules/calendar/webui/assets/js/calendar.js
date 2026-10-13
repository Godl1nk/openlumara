/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
   calendar sidebar panel + event modal logic. Talks to /api/ext/calendar/. */
const CALENDAR_PANEL = {
    events: [],
    channels: [],
    loading: false,
    loaded: false,
    error: "",
    days: 14,
    editing: null,
    form: { title: "", date: "", time: "", notify: true, channel: "" },
    saving: false,

    async refresh(force = false) {
        if (force || !this.loaded) {
            await this.load();
        }
        if (!this.channels.length) {
            await this.loadChannels();
        }
    },

    async load() {
        this.loading = true;
        this.error = "";

        try {
            this.events = await simpleApiFetch(`/api/ext/calendar/upcoming?days=${this.days}`) || [];
            this.loaded = true;
        } catch (e) {
            this.error = this.errorText(e);
        } finally {
            this.loading = false;
        }
    },

    async loadChannels() {
        try {
            this.channels = await simpleApiFetch("/api/ext/calendar/channels") || [];
        } catch (e) {
            this.channels = [];
        }
    },

    groups() {
        const out = [];
        const byKey = {};

        for (const ev of this.events) {
            const key = (ev.date || "").substring(0, 10);
            if (!byKey[key]) {
                byKey[key] = { key: key, label: this.dayLabel(key), items: [] };
                out.push(byKey[key]);
            }
            byKey[key].items.push(ev);
        }

        return out;
    },

    dayLabel(key) {
        const today = new Date();
        const todayKey = this.localDateKey(today);
        const tomorrow = new Date(today);
        tomorrow.setDate(tomorrow.getDate() + 1);

        if (key === todayKey) return "today";
        if (key === this.localDateKey(tomorrow)) return "tomorrow";

        const parts = key.split("-").map(Number);
        if (parts.length !== 3) return key;

        const date = new Date(parts[0], parts[1] - 1, parts[2]);
        return date.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
    },

    localDateKey(date) {
        const y = date.getFullYear();
        const m = String(date.getMonth() + 1).padStart(2, "0");
        const d = String(date.getDate()).padStart(2, "0");
        return `${y}-${m}-${d}`;
    },

    fmtTime(dateStr) {
        const parts = (dateStr || "").split("T");
        if (parts.length < 2) return "--:--";
        return parts[1].substring(0, 5);
    },

    isPast(ev) {
        return new Date(ev.date).getTime() < Date.now();
    },

    openCreate() {
        const now = new Date();
        now.setMinutes(now.getMinutes() + 60);

        this.editing = { id: null };
        this.form = {
            title: "",
            date: this.localDateKey(now),
            time: `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`,
            notify: true,
            channel: "",
        };
        this.error = "";
        Alpine.store("ui").openModal("calendar_event");
    },

    openEdit(ev) {
        this.editing = { id: ev.id };
        this.form = {
            title: ev.title || "",
            date: (ev.date || "").substring(0, 10),
            time: this.fmtTime(ev.date),
            notify: !!ev.notify,
            channel: ev.notify_channel || "",
        };
        this.error = "";
        Alpine.store("ui").openModal("calendar_event");
    },

    closeModal() {
        this.editing = null;
        this.error = "";
        Alpine.store("ui").closeModal();
    },

    async save() {
        if (this.saving) return;

        const title = this.form.title.trim();
        if (!title || !this.form.date) {
            this.error = "a title and a date are required";
            return;
        }

        this.saving = true;
        this.error = "";

        try {
            if (this.editing && this.editing.id) {
                await simpleApiPost("/api/ext/calendar/update", {
                    id: this.editing.id,
                    title: title,
                    date: this.form.date,
                    time: this.form.time || "00:00",
                    notify: this.form.notify,
                    notify_channel: this.form.channel || null,
                });
            } else {
                await simpleApiPost("/api/ext/calendar/create", {
                    title: title,
                    date: this.form.date,
                    time: this.form.time || "00:00",
                    notify: this.form.notify,
                    notify_channel: this.form.channel || null,
                });
            }

            await this.load();
            this.closeModal();
        } catch (e) {
            this.error = this.errorText(e);
        } finally {
            this.saving = false;
        }
    },

    async remove(ev) {
        if (!window.confirm(`Delete event "${ev.title}"?`)) return;

        this.error = "";
        try {
            await simpleApiPost("/api/ext/calendar/delete", { id: ev.id });
            await this.load();
        } catch (e) {
            this.error = this.errorText(e);
        }
    },

    errorText(e) {
        if (e && typeof e === "object") return e.message || JSON.stringify(e);
        return String(e);
    }
};

document.addEventListener("alpine:init", () => {
    Alpine.store("calendarPanel", CALENDAR_PANEL);
});

// -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
// fresh Proxy per mount (see shell.js shellTermComponent for why x-data
// must never receive the store object directly)
function calendarPanelComponent() {
    const target = {};
    const src = () => Alpine.store("calendarPanel") || CALENDAR_PANEL;

    return new Proxy(target, {
        get(t, key) {
            if (key === Symbol.unscopables) return undefined;
            if (key in t) return t[key];
            const val = src()[key];
            return typeof val === "function" ? val.bind(src()) : val;
        },
        set(t, key, value) {
            if (key in t) {
                t[key] = value;
                return true;
            }
            src()[key] = value;
            return true;
        },
        has(t, key) {
            return key in t || key in src();
        },
        ownKeys() {
            return [...new Set([...Reflect.ownKeys(target), ...Object.keys(src())])];
        },
        getOwnPropertyDescriptor(t, key) {
            if (key in t) return Reflect.getOwnPropertyDescriptor(t, key);
            if (key in src()) {
                return { value: src()[key], enumerable: true, configurable: true, writable: true };
            }
            return undefined;
        },
    });
}
