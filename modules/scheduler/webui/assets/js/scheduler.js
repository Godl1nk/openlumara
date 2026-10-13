/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
   scheduler sidebar panel + job modal logic. Talks to /api/ext/scheduler/. */
const SCHEDULER_PANEL = {
    jobs: [],
    channels: [],
    loading: false,
    loaded: false,
    error: "",
    editing: null,
    saving: false,
    form: { action: "", channel: "", recurring: false, mode: "relative", duration: "", time: "", weekday: "" },

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
            this.jobs = await simpleApiFetch("/api/ext/scheduler/list") || [];
            this.loaded = true;
        } catch (e) {
            this.error = this.errorText(e);
        } finally {
            this.loading = false;
        }
    },

    async loadChannels() {
        try {
            this.channels = await simpleApiFetch("/api/ext/scheduler/channels") || [];
        } catch (e) {
            this.channels = [];
        }
    },

    fmtWhen(iso) {
        if (!iso) return "";

        const date = new Date(iso);
        if (Number.isNaN(date.getTime())) return String(iso);

        return date.toLocaleString(undefined, {
            weekday: "short", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
        });
    },

    durationFromRecur(r) {
        const parts = [];
        for (const key of ["weeks", "days", "hours", "minutes", "seconds"]) {
            if (r && r[key]) {
                parts.push(`${r[key]}${key[0]}`);
            }
        }
        return parts.join(" ") || "1h";
    },

    openCreate() {
        this.editing = { id: null };
        this.form = { action: "", channel: "", recurring: false, mode: "relative", duration: "1h", time: "09:00", weekday: "" };
        this.error = "";
        Alpine.store("ui").openModal("scheduler_job");
    },

    openEdit(job) {
        const r = job.recurs_in || {};
        let mode = "relative";
        let duration = "1h";
        let time = "09:00";
        let weekday = "";

        if (job.recurring && r.target_hour != null) {
            mode = "clock";
            time = `${String(r.target_hour).padStart(2, "0")}:${String(r.target_minute || 0).padStart(2, "0")}`;
            weekday = r.target_weekday != null ? String(r.target_weekday) : (r.weekdays_only ? "weekdays" : "");
        } else if (job.recurring) {
            mode = "relative";
            duration = this.durationFromRecur(r);
        } else {
            // one-time job: edit as clock at its trigger's time of day
            mode = "clock";
            time = (job.trigger_time || "").substring(11, 16) || "09:00";
        }

        this.editing = { id: job.id };
        this.form = {
            action: job.action || "",
            channel: job.channel || "",
            recurring: !!job.recurring,
            mode: mode,
            duration: duration,
            time: time,
            weekday: weekday,
        };
        this.error = "";
        Alpine.store("ui").openModal("scheduler_job");
    },

    closeModal() {
        this.editing = null;
        this.error = "";
        Alpine.store("ui").closeModal();
    },

    payload() {
        return {
            action: this.form.action.trim(),
            channel: this.form.channel || null,
            recurring: !!this.form.recurring,
            mode: this.form.mode,
            duration: this.form.mode === "relative" ? this.form.duration : "",
            time: this.form.mode === "clock" ? this.form.time : "",
            weekday: this.form.mode === "clock" ? this.form.weekday : "",
        };
    },

    async save() {
        if (this.saving) return;

        if (!this.form.action.trim()) {
            this.error = "the job needs an action";
            return;
        }

        this.saving = true;
        this.error = "";

        try {
            if (this.editing && this.editing.id) {
                await simpleApiPost("/api/ext/scheduler/update", Object.assign({ id: this.editing.id }, this.payload()));
            } else {
                await simpleApiPost("/api/ext/scheduler/create", this.payload());
            }

            await this.load();
            this.closeModal();
        } catch (e) {
            this.error = this.errorText(e);
        } finally {
            this.saving = false;
        }
    },

    async remove(job) {
        const preview = (job.action || "").substring(0, 60);
        if (!window.confirm(`Delete this job?\n\n"${preview}${(job.action || "").length > 60 ? ".." : ""}"`)) return;

        this.error = "";
        try {
            await simpleApiPost("/api/ext/scheduler/delete", { id: job.id });
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
    Alpine.store("schedulerPanel", SCHEDULER_PANEL);
});

// -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
// fresh Proxy per mount (see shell.js shellTermComponent for why x-data
// must never receive the store object directly)
function schedulerPanelComponent() {
    const target = {};
    const src = () => Alpine.store("schedulerPanel") || SCHEDULER_PANEL;

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
