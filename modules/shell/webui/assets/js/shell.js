/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
   shell terminal logic. one shared store (shellTerm) powers both the
   sidebar panel and the pop-out modal, so the scrollback is identical in
   both. commands go through /api/ext/shell/run -> the module's sandboxed
   run(), so timeouts/output limits/isolation all apply. */
const SHELL_TERM = {
    lines: [],
    input: "",
    history: [],
    histIdx: -1,
    running: false,
    booted: false,
    maxLines: 500,

    async boot() {
        if (this.booted) return;
        this.booted = true;

        try {
            const status = await simpleApiFetch("/api/ext/shell/status");
            this.push("info", "openlumara sandbox shell");
            for (const line of String(status || "").split("\n")) {
                if (line.trim()) this.push("dim", line);
            }
        } catch (e) {
            this.push("info", "openlumara sandbox shell");
        }

        this.push("dim", "type a command and press enter. 'clear' clears the screen.");
        this.scroll();
    },

    push(type, text) {
        this.lines.push({ type: type, text: text });

        if (this.lines.length > this.maxLines) {
            this.lines.splice(0, this.lines.length - this.maxLines);
        }

        Alpine.nextTick(() => this.scroll());
    },

    scroll() {
        for (const el of document.querySelectorAll(".term-out")) {
            el.scrollTop = el.scrollHeight;
        }
    },

    async submit() {
        if (this.running) return;

        const cmd = this.input.trim();
        this.input = "";

        if (!cmd) {
            this.scroll();
            return;
        }

        this.history.unshift(cmd);
        this.histIdx = -1;

        this.push("cmd", cmd);

        if (cmd === "clear" || cmd === "cls") {
            this.lines = [];
            return;
        }

        this.running = true;

        try {
            const res = await simpleApiPost("/api/ext/shell/run", { command: cmd });
            this.renderResult(res);
        } catch (e) {
            // the run route returns failures (timeouts etc.) as an error
            // payload that still carries whatever stdout/stderr made it out
            if (e && typeof e === "object") {
                this.renderResult(e);
                if (e.errors) this.push("err", e.errors.join("\n"));
                else if (e.message) this.push("err", String(e.message));
            } else {
                this.push("err", String(e));
            }
        } finally {
            this.running = false;
            this.scroll();
        }
    },

    renderResult(res) {
        if (!res || typeof res !== "object") {
            if (res) this.push("out", String(res));
            return;
        }

        if (res.stdout) this.push("out", res.stdout);
        if (res.stderr) this.push("err", res.stderr);

        if (res.truncation_note) this.push("dim", res.truncation_note);
        if (res.errors && Array.isArray(res.errors)) this.push("err", res.errors.join("\n"));

        if (res.exit_code != null && res.exit_code !== 0) {
            this.push("dim", `[exit ${res.exit_code}]`);
        }

        if (!res.stdout && !res.stderr && !(res.errors && res.errors.length)) {
            this.push("dim", "[no output]");
        }
    },

    histUp() {
        if (!this.history.length) return;
        this.histIdx = Math.min(this.histIdx + 1, this.history.length - 1);
        this.input = this.history[this.histIdx];
    },

    histDown() {
        if (this.histIdx < 0) return;
        this.histIdx -= 1;
        this.input = this.histIdx < 0 ? "" : this.history[this.histIdx];
    },

    clear() {
        this.lines = [];
    },

    focusInput(el) {
        const term = el.closest(".term");
        if (!term) return;

        const input = term.querySelector(".term-capture");
        if (input) input.focus();
    },

    popout() {
        Alpine.store("ui").openModal("shell_terminal");
    },

    closeModal() {
        Alpine.store("ui").closeModal();
    }
};

document.addEventListener("alpine:init", () => {
    Alpine.store("shellTerm", SHELL_TERM);
});

// -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
// x-data must NEVER receive the shared reactive store directly: Alpine's
// injectMagics() runs Object.defineProperty() for $nextTick/$refs/$el/...
// onto whatever x-data returns, with configurable:false. that works for
// the first component (sidebar) and throws "Cannot redefine property:
// $nextTick" for the second one mounting the same object (pop-out modal),
// killing every binding in the modal subtree. so each component gets its
// own fresh proxy: magics land on its private throwaway target, while
// all real reads/writes forward to the shared store (scrollback and
// pending input stay in sync between sidebar and modal).
function shellTermComponent() {
    const target = {};
    const src = () => Alpine.store("shellTerm") || SHELL_TERM;

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
            // MUST include the target's own keys: Alpine defines its magic
            // properties ($nextTick, $refs, ...) on this proxy (they land on
            // the private target, non-configurable) and then runs
            // Object.getOwnPropertyDescriptors() over the object - if
            // ownKeys omitted them the engine throws a proxy invariant
            // TypeError. store keys are merged on top, deduped.
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
