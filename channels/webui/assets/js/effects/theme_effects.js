/*
 * Optional animated background layers for themes.
 *
 * A theme family opts in from its JSON:
 *   "effects": { "type": "embers" | "stars", "intensity": 1 }
 * The theming store publishes the choice via <html data-theme-effect> and a
 * 'theme-effect-changed' event. Rendering is canvas-only (transform/opacity
 * work happens on the compositor, no layout), pointer-interactive, paused
 * while the tab is hidden and disabled under prefers-reduced-motion.
 * "aurora" is a CSS-only effect and needs no code here.
 */
(function () {
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');

    let canvas = null;
    let ctx = null;
    let raf = 0;
    let last = 0;
    let type = null;
    let intensity = 1;
    let w = 0;
    let h = 0;
    let dpr = 1;
    let particles = [];
    let sprite = null;

    const pointer = { x: -9999, y: -9999, active: false };
    const rand = (a, b) => a + Math.random() * (b - a);

    function cssVar(name, fallback) {
        const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
        return value || fallback;
    }

    function ensureCanvas() {
        if (canvas) return;
        canvas = document.createElement('canvas');
        canvas.id = 'theme-effect-canvas';
        canvas.setAttribute('aria-hidden', 'true');
        document.body.appendChild(canvas);
        ctx = canvas.getContext('2d', { alpha: true });
    }

    function destroyCanvas() {
        if (canvas) canvas.remove();
        canvas = null;
        ctx = null;
        sprite = null;
    }

    function resize() {
        if (!canvas) return;
        dpr = Math.min(window.devicePixelRatio || 1, 2);
        w = window.innerWidth;
        h = window.innerHeight;
        canvas.width = Math.max(1, Math.round(w * dpr));
        canvas.height = Math.max(1, Math.round(h * dpr));
        canvas.style.width = w + 'px';
        canvas.style.height = h + 'px';
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    // one pre-rendered glow sprite beats a gradient per particle per frame
    function makeSprite() {
        const size = 64;
        const el = document.createElement('canvas');
        el.width = el.height = size;
        const g = el.getContext('2d');
        const grad = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
        const color = cssVar('--effect-color', cssVar('--accent', '#ff7a3d'));
        grad.addColorStop(0, color);
        grad.addColorStop(0.4, color);
        grad.addColorStop(1, 'transparent');
        g.fillStyle = grad;
        g.fillRect(0, 0, size, size);
        return el;
    }

    function seed() {
        if (type === 'embers') {
            const count = Math.round(Math.min(90, (w * h) / 24000) * intensity);
            particles = Array.from({ length: count }, () => ({
                x: rand(0, w),
                y: rand(0, h),
                r: rand(1.1, 3.2),
                vy: rand(8, 26),
                sway: rand(0.4, 1.2),
                phase: rand(0, Math.PI * 2),
                a: rand(0.25, 0.75),
            }));
        } else {
            const count = Math.round(Math.min(160, (w * h) / 12000) * intensity);
            particles = Array.from({ length: count }, () => ({
                x: rand(0, w),
                y: rand(0, h),
                r: rand(0.4, 1.4),
                phase: rand(0, Math.PI * 2),
                speed: rand(0.3, 1.1),
                a: rand(0.25, 0.8),
            }));
        }
    }

    function drawEmbers(dt, t) {
        ctx.globalCompositeOperation = 'lighter';
        for (const p of particles) {
            p.y -= p.vy * dt;
            p.x += Math.sin(t * p.sway + p.phase) * 0.35;

            if (pointer.active) {
                const dx = p.x - pointer.x;
                const dy = p.y - pointer.y;
                const d2 = dx * dx + dy * dy;
                if (d2 < 130 * 130 && d2 > 1) {
                    const d = Math.sqrt(d2);
                    const push = ((130 - d) / 130) * 60 * dt;
                    p.x += (dx / d) * push;
                    p.y += (dy / d) * push;
                }
            }

            if (p.y < -8) {
                p.y = h + 8;
                p.x = rand(0, w);
            }
            if (p.x < -8) p.x = w + 8;
            else if (p.x > w + 8) p.x = -8;

            ctx.globalAlpha = p.a;
            ctx.drawImage(sprite, p.x - p.r * 3, p.y - p.r * 3, p.r * 6, p.r * 6);
        }
        ctx.globalAlpha = 1;
        ctx.globalCompositeOperation = 'source-over';
    }

    function drawStars(t) {
        const ox = pointer.active ? (pointer.x - w / 2) * 0.012 : 0;
        const oy = pointer.active ? (pointer.y - h / 2) * 0.012 : 0;
        ctx.fillStyle = cssVar('--effect-color', '#cfd8ff');
        for (const p of particles) {
            ctx.globalAlpha = p.a * (0.45 + 0.55 * (0.5 + 0.5 * Math.sin(t * p.speed + p.phase)));
            ctx.beginPath();
            ctx.arc(p.x + ox, p.y + oy, p.r, 0, Math.PI * 2);
            ctx.fill();
        }
        ctx.globalAlpha = 1;
    }

    function frame(now) {
        raf = 0;
        if (!ctx || !type) return;
        const dt = Math.min(0.05, (now - last) / 1000 || 0.016);
        last = now;
        const t = now / 1000;

        ctx.clearRect(0, 0, w, h);
        if (type === 'embers') drawEmbers(dt, t);
        else drawStars(t);

        raf = requestAnimationFrame(frame);
    }

    function start() {
        ensureCanvas();
        resize();
        sprite = type === 'embers' ? makeSprite() : null;
        seed();
        last = performance.now();
        if (!raf) raf = requestAnimationFrame(frame);
    }

    function pause() {
        if (raf) cancelAnimationFrame(raf);
        raf = 0;
    }

    function stop() {
        pause();
        particles = [];
        destroyCanvas();
    }

    function restart() {
        const running = type;
        stop();
        type = running;
        if (type && !reduced.matches && !document.hidden) start();
    }

    function setEffect(effects) {
        const next = effects && effects.type ? String(effects.type) : null;
        const nextIntensity = effects && effects.intensity != null ? (Number(effects.intensity) || 1) : 1;
        // aurora is pure CSS: make sure the canvas layer is gone
        if (next === 'aurora') {
            stop();
            type = null;
            return;
        }
        if (next === type && nextIntensity === intensity) return;
        stop();
        type = (next === 'embers' || next === 'stars') ? next : null;
        intensity = nextIntensity;
        if (type && !reduced.matches && !document.hidden) start();
    }

    window.addEventListener('theme-effect-changed', (event) => setEffect(event.detail));
    // a theme swap changes the accent colours: rebuild the sprite/particles
    window.addEventListener('theme-changed', () => { if (type) restart(); });
    window.addEventListener('resize', () => { if (type) { resize(); seed(); } }, { passive: true });
    window.addEventListener('pointermove', (event) => {
        pointer.x = event.clientX;
        pointer.y = event.clientY;
        pointer.active = true;
    }, { passive: true });
    window.addEventListener('pointerleave', () => { pointer.active = false; });

    document.addEventListener('visibilitychange', () => {
        if (document.hidden) pause();
        else if (type && !reduced.matches && !raf) start();
    });

    reduced.addEventListener('change', () => {
        if (reduced.matches) stop();
        else if (type) restart();
    });

    function boot() {
        const root = document.documentElement;
        setEffect({
            type: root.dataset.themeEffect || null,
            intensity: Number(root.dataset.themeEffectIntensity || 1),
        });
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
    else boot();
})();
