/*
 * -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-15)
 * real rendered heights of lazy-mounted turns, keyed by the turn object
 * (which mergeTurnHistory keeps identity-stable). lives outside the alpine
 * store on purpose: no reactivity needed on it, and it keeps the proxy
 * from ever wrapping the WeakMap.
 */
const _turnHeights = new WeakMap();

/*
 * -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17) (02:45)
 * per-element lerp-chase state (active rAF id) and a marker for elements
 * whose user-input interrupt listeners are already wired up
 */
const _chases = new WeakMap();
const _interruptBound = new WeakSet();

UI_STORE = {
    scrollThreshold: 50,
    errors: [],
    currentModal: null,
    notice: null,

    shouldScroll: true,
    scrollToTurnIndex: null,

    /*
     * -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17) (02:45)
     * lerp-chase streaming autoscroll: instead of native smooth scroll (no
     * speed control), each animation frame moves scrollTop a fraction of the
     * remaining distance toward the bottom. the target is re-read every
     * frame, so tokens arriving mid-chase are folded into the same glide.
     * scrollFollowSpeed is the knob: 0.2 = glidey, 0.5 = snappy, 1 = instant.
     * while a chase is in flight its intermediate positions are suppressed
     * from bottom-detection (they would flip shouldScroll off and stall the
     * follow); a real wheel/touch cancels the chase and resumes tracking.
     */
    scrollFollowSpeed: 0.2,
    _suppressScroll: false,

    _updateShouldScroll(el) {
        const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
        this.shouldScroll = distFromBottom < this.scrollThreshold;
    },

    _stopChase(el) {
        const chase = _chases.get(el);
        if (!chase) return;
        if (chase.raf) cancelAnimationFrame(chase.raf);
        if (chase.mo) chase.mo.disconnect();
        _chases.delete(el);
        this._suppressScroll = false;
    },

    _chaseScrollToBottom(el) {
        if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
            this._stopChase(el);
            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
            // instant: global scroll-behavior:smooth would animate this jump
            el.scrollTo({ top: el.scrollHeight, behavior: 'instant' });
            return;
        }

        let chase = _chases.get(el);
        if (!chase) {
            chase = { raf: null, mo: null };
            _chases.set(el, chase);
            this._suppressScroll = true;

            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
            // keep gliding while content grows: streamed tokens mutate the
            // dom without re-calling scrollToBottom, so without this the
            // chase dies the moment remaining < 1 and a later token restarts
            // it from scratch (visible stutter). cheap coalesced re-arm.
            chase.mo = new MutationObserver(() => {
                if (chase.raf === null) chase.raf = requestAnimationFrame(step);
            });
            chase.mo.observe(el, { childList: true, subtree: true });

            // user input wins: give up the chase and let onScroll track
            // their real position again. bound once per element.
            if (!_interruptBound.has(el)) {
                _interruptBound.add(el);
                const stop = () => {
                    this._stopChase(el);
                    this._updateShouldScroll(el);
                };
                el.addEventListener('wheel', stop, { passive: true });
                el.addEventListener('touchstart', stop, { passive: true });
            }
        }

        if (chase.raf) return; // already chasing; the step re-reads the target

        const step = () => {
            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
            // scrollTo with behavior:'instant' overrides the global
            // scroll-behavior:smooth. with plain scrollTop writes, each frame
            // spawned a fresh browser smooth-scroll animation that the next
            // frame interrupted: the chase double-eased (our lerp + browser
            // easing) and read back lagging animated positions, so it crawled
            // and turned choppy as scroll deltas grew with the chat.
            // instant writes make the lerp the only easing in play.
            const target = el.scrollHeight - el.clientHeight;
            const remaining = target - el.scrollTop;
            if (Math.abs(remaining) < 1) {
                el.scrollTo({ top: target, behavior: 'instant' });
                this._stopChase(el);
                this._updateShouldScroll(el);
                return;
            }
            el.scrollTo({ top: el.scrollTop + remaining * this.scrollFollowSpeed, behavior: 'instant' });
            chase.raf = requestAnimationFrame(step);
        };
        chase.raf = requestAnimationFrame(step);
    },

    /*
     * -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-15)
     * lazy-mount scroll stability:
     * - _turnHeights remembers the real rendered height of a turn so its
     *   placeholder is exact when it remounts (WeakMap keyed by the turn
     *   object, which mergeTurnHistory keeps identity-stable).
     * - _mountPass() manually compensates scrollTop when a turn's height
     *   changes above the viewport, replacing chrome's scroll anchoring
     *   (disabled via overflow-anchor: none), which fights user scroll and
     *   causes the "skipping past messages" jump.
     */
    captureTurnHeight(turn, el) {
        _turnHeights.set(turn, el.offsetHeight);
    },

    turnPlaceholderHeight(turn) {
        const cached = _turnHeights.get(turn);
        if (cached) return cached;

        // rough first-visit estimate; _mountPass() compensates the error
        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
        // null-guard: a malformed/null message shouldn't kill the whole
        // lazy-mount placeholder computation
        const chars = (turn.messages || []).reduce(
            (n, m) => n + (m && typeof m.content === 'string' ? m.content.length : 200), 0
        );
        return Math.min(400, Math.max(40, Math.round(chars / 6)));
    },

    /*
     * -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-11)
     * bottom-up lazy mount controller.
     *
     * why this replaced the x-intersect approach: the old code stored
     * `rendered` in each turn element's x-data and toggled it on observer
     * EDGE events. two ways that lost messages: (1) x-for keys turns by
     * index, so replacing turnHistory (chat switch, or a reload where a
     * turn's hash changed) reuses the old elements WITHOUT re-running
     * their x-data - a stale rendered=false stranded turns as invisible
     * placeholders inside the viewport, and with no new intersection
     * transition the enter handler never re-fired; (2) an instant
     * programmatic jump (scrollTo behavior:'instant') can carry an element
     * through the mount zone between IO deliveries - no net transition,
     * no mount, same stranded placeholder.
     *
     * the new approach is LEVEL-triggered: turnMounted (the single source
     * of truth, in the store so element reuse can never strand it) is
     * recomputed from live geometry on every rAF-coalesced pass. a pass
     * always sees the current truth, so nothing can stay stuck unmounted.
     */
    turnMounted: {},
    mountMargin: 800,      // px: mount turns approaching the viewport
    unmountMargin: 2500,   // px: recycle mounted dom that drifted far outside
    _mountRaf: null,

    isTurnMounted(turnIndex) {
        if (this.turnMounted[turnIndex]) return true;
        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-12)
        // live streaming turns are ALWAYS mounted: the live turn now lives
        // in turnHistory (it gets promoted in place on stream_complete),
        // and recycling it mid-stream would blank out the reply as it types.
        const turn = Alpine.store('chat').turnHistory?.[turnIndex];
        return Boolean(turn && turn.live === true);
    },

    resetTurnMounts() {
        this.turnMounted = {};
    },

    /*
     * bottom-up initial render: mount the newest turn first, then walk
     * upward until the cumulative estimated height covers ~2 viewports.
     * opening a chat then shows the tail with real (stable) heights right
     * where the viewport lands, so scrollToBottom is a single landing
     * instead of an aggressive timed autoscroll sweeping the whole chat.
     */
    prepareBottomWindow() {
        const container = document.getElementById('messages');
        const turns = Alpine.store('chat').turnHistory;
        if (!container || !turns || turns.length === 0) return;

        const budget = Math.max(container.clientHeight * 2, 600);
        let total = 0;
        for (let i = turns.length - 1; i >= 0; i--) {
            this.turnMounted[i] = true;
            total += this.turnPlaceholderHeight(turns[i]);
            if (total >= budget) break;
        }
    },

    /*
     * called after every turnHistory mutation: prune mount entries for
     * turns that no longer exist, keep the newest turns mounted (a fresh
     * message must never flash in as a placeholder), schedule a pass.
     */
    syncMountWindows() {
        const turns = Alpine.store('chat').turnHistory;
        const n = (turns || []).length;

        for (const k of Object.keys(this.turnMounted)) {
            if (Number(k) >= n) delete this.turnMounted[k];
        }
        for (let i = Math.max(0, n - 2); i < n; i++) this.turnMounted[i] = true;

        this.updateMounts();
    },

    updateMounts() {
        if (this._mountRaf !== null) return;
        this._mountRaf = requestAnimationFrame(() => {
            this._mountRaf = null;
            this._mountPass();
        });
    },

    _mountPass() {
        const container = document.getElementById('messages');
        if (!container) return;
        const turns = Alpine.store('chat').turnHistory;
        if (!turns || turns.length === 0) return;

        const cRect = container.getBoundingClientRect();
        const mountTop = cRect.top - this.mountMargin;
        const mountBottom = cRect.bottom + this.mountMargin;
        const farTop = cRect.top - this.unmountMargin;
        const farBottom = cRect.bottom + this.unmountMargin;

        const mounts = [];

        container.querySelectorAll('[data-turn-index]').forEach(el => {
            const i = Number(el.dataset.turnIndex);
            const turn = turns[i];
            if (!turn) return;

            const r = el.getBoundingClientRect();
            if (this.turnMounted[i]) {
                if (r.bottom < farTop || r.top > farBottom) {
                    // capture first: the placeholder then has the exact
                    // height, so unmounting never shifts the document
                    this.captureTurnHeight(turn, el);
                    delete this.turnMounted[i];
                }
            } else if (r.bottom > mountTop && r.top < mountBottom) {
                // 'above' = fully above the viewport: only those get a
                // scroll compensation when they grow. an element that
                // straddles the top edge is (partly) what the user is
                // looking at: compensating it would jump the view, so we
                // let it visibly fill in instead.
                mounts.push({ i, above: r.bottom <= cRect.top, h: el.offsetHeight });
            }
        });

        if (mounts.length === 0) return;

        (async () => {
            for (const m of mounts) this.turnMounted[m.i] = true;

            await Alpine.nextTick();

            // turns mounting above the viewport push the visible content
            // down: compensate scrollTop by their growth (placeholder to
            // real height). instant: a smooth compensation would drift.
            let shift = 0;
            for (const m of mounts) {
                const el = container.querySelector(`[data-turn-index="${m.i}"]`);
                if (el && m.above) shift += el.offsetHeight - m.h;
            }
            if (shift) container.scrollTo({ top: container.scrollTop + shift, behavior: 'instant' });

            // heights may have moved the window: re-evaluate once more.
            // safe: a pass with nothing to mount does not reschedule.
            this.updateMounts();
        })();
    },

    windowWidth: window.innerWidth,
    isMobile: false,

    showSidebar: true,

    // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-14)
    // collapsed sidebar: only the vertical tab strip stays visible.
    // toggled by clicking the already-active sidebar tab (sidebar.html);
    // lives in the ui store so #sidebar itself can shrink via a class.
    sidebarCollapsed: false,

    expandReasoning: true,

    async init() {
        // check if this is a phone
        this.windowWidth = window.innerWidth;
        this.isMobile = window.innerWidth <= 768;

        // hide sidebar on mobile (in favor of a hamburger button)
        this.showSidebar = !this.isMobile;

        // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-14)
        // restore the collapsed-sidebar preference (default: expanded)
        this.sidebarCollapsed = localStorage.getItem("sidebarCollapsed") === 'true';

        this.expandReasoning = localStorage.getItem("expandReasoning") !== 'false';

        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-11)
        // a resize moves the mount window: re-evaluate lazily-mounted turns
        window.addEventListener('resize', () => this.updateMounts());
    },

    async toggleSidebar() {
        this.showSidebar = !this.showSidebar;
    },

    async openModal(name, settingsCategory = 'appearance') {
        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-12)
        // opening another modal while settings is dirty used to silently
        // auto-save; now it asks first. cancelling keeps the settings
        // modal open. (the settings modal unmounts on switch, so its
        // inline close-prompt can't ride along here - native confirm it is)
        if (this.currentModal === 'settings' && name !== 'settings') {
            const settings = Alpine.store('settings');
            if (settings.hasChanges &&
                !confirm('You have unsaved settings changes. Open the other dialog without saving?')) {
                return;
            }
        }

        if (name === 'settings') {
            Alpine.store('settings').activeCategory = settingsCategory;
        }
        this.currentModal = name;

        /*
         * post-open actions
         */

        if (name === 'logs') {
            // scroll down to the bottom
            await Alpine.nextTick();

            const el = document.getElementById('log-container');
            if (el) el.scrollTop = el.scrollHeight;
        }
    },
    async closeModal() {
        this.currentModal = null;
    },

    /*
     * Called from @scroll on the messages container.
     * Toggles shouldScroll based on whether the user is near the bottom.
     */
    onScroll(containerId = 'messages') {
        const el = document.getElementById(containerId);
        if (!el) return;

        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-11)
        // every scroll moves the mount window: schedule a (rAF-coalesced)
        // lazy-mount pass alongside the bottom-tracking
        this.updateMounts();

        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17) (02:25)
        // ignore the intermediate positions of our own smooth autoscroll;
        // the resting position is evaluated when the animation settles.
        if (this._suppressScroll) return;

        this._updateShouldScroll(el);
    },

    /*
     * -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01) (23:30)
     * instant jump-to-bottom, shared by forceScrollToBottom() and the
     * instant variant of scrollToBottom(). cancels any in-flight chase so
     * its per-frame writes don't fight the jumps.
     *
     * lazy-mounted turns change scrollHeight asynchronously: the
     * intersectionobserver only mounts placeholders into real dom a
     * frame *after* we scroll, so a single nextTick scroll lands above
     * the true bottom. iterate (scroll -> wait a frame -> check if the
     * height changed) until it settles, so mounting near the bottom is
     * always followed by another scroll to the new bottom.
     * aborts if the user grabs the scrollbar mid-flight.
     */
    async _jumpToBottom(el) {
        this._stopChase(el);

        let lastHeight = -1;
        for (let i = 0; i < 24; i++) {
            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-11)
            // keep the lazy-mount window in sync with each jump: with the
            // bottom window pre-mounted (prepareBottomWindow) this settles
            // in a couple of iterations instead of sweeping the whole chat
            this.updateMounts();
            await Alpine.nextTick();
            // scrollTo with behavior:'instant' overrides the global
            // scroll-behavior:smooth. with smooth, each jump animated through
            // the whole chat and the lazy-mount zone mounted everything along
            // the way down. instant jumps land at the bottom directly.
            el.scrollTo({ top: el.scrollHeight, behavior: 'instant' });
            await new Promise(resolve => requestAnimationFrame(resolve));

            if (!this.shouldScroll) break;
            if (el.scrollHeight === lastHeight) break;
            lastHeight = el.scrollHeight;
        }
    },

    /*
     * -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01) (23:30)
     * instant=true skips the lerp-chase glide entirely and jumps straight
     * to the bottom: use this after chat reloads (e.g. stream_complete)
     * where a smooth scroll across the whole chat looks awful.
     */
    async scrollToBottom(containerId = 'messages', instant = false) {
        if (!this.shouldScroll) return;

        const el = document.getElementById(containerId);
        if (!el) return;

        if (instant) {
            await this._jumpToBottom(el);
            return;
        }

        // lerp chase for the streaming follow; tokens arriving mid-chase
        // just extend the glide since the target is re-read every frame
        Alpine.nextTick(() => {
            this._chaseScrollToBottom(el);
        });
    },

    async forceScrollToBottom(containerId = 'messages') {
        const el = document.getElementById(containerId);
        if (!el) return;

        this.shouldScroll = true;

        await this._jumpToBottom(el);
    },

    async scrollToTurn(turnIndex) {
        if (turnIndex === null || turnIndex === undefined) return;

        /*
         * -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-15)
         * the turn wrapper always exists but its contents may be an
         * unmounted placeholder, which grows into real dom once it nears
         * the viewport - so re-center iteratively until the scroll
         * position settles instead of centering once on a fake height.
         */
        const container = document.getElementById('messages');
        if (!container) return;

        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17) (02:45)
        // a running chase would fight the re-centering loop below
        this._stopChase(container);

        let lastTop = -1;
        for (let i = 0; i < 24; i++) {
            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-11)
            // mount the turns the jumps sweep through, so heights along the
            // way (and the target itself) are real while re-centering
            this.updateMounts();
            await Alpine.nextTick();

            const el = document.querySelector(`[data-turn-index="${turnIndex}"]`);
            if (!el) { break; }

            const containerRect = container.getBoundingClientRect();
            const elementRect = el.getBoundingClientRect();
            const offset = elementRect.top - containerRect.top - (containerRect.height / 2) + (elementRect.height / 2);
            // instant jump: smooth would sweep the lazy-mount zone through
            // every turn between here and the target
            container.scrollTo({ top: container.scrollTop + offset, behavior: 'instant' });

            await new Promise(resolve => requestAnimationFrame(resolve));
            if (container.scrollTop === lastTop) break;
            lastTop = container.scrollTop;
        }

        this.scrollToTurnIndex = null;
    }
}
