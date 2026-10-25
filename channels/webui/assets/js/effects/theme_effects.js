/*
 * Optional animated background layers for themes.
 *
 * A theme family opts in from its JSON:
 *   "effects": { "type": "<name>", "intensity": 1, "trail": 0.08 }
 * Types: embers | stars | network | flow | warp | bokeh  (aurora is CSS-only)
 * The theming store publishes the choice via <html data-theme-effect> and a
 * 'theme-effect-changed' event.
 *
 * Rendering is canvas-only (no layout work), pointer-interactive, paused
 * while the tab is hidden and disabled under prefers-reduced-motion.
 * "trail" > 0 keeps motion trails by fading the previous frame instead of
 * clearing it.
 */
(function () {
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
    const CANVAS_TYPES = new Set(['embers', 'stars', 'network', 'flow', 'warp', 'bokeh', 'mesh']);

    let canvas = null;
    let ctx = null;
    let raf = 0;
    let last = 0;
    let type = null;
    let intensity = 1;
    let trailAlpha = 0;
    let w = 0;
    let h = 0;
    let dpr = 1;
    let particles = [];
    let sprites = {};

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
        sprites = {};
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
    function makeSprite(size, color) {
        const key = size + color;
        if (sprites[key]) return sprites[key];
        const el = document.createElement('canvas');
        el.width = el.height = size;
        const g = el.getContext('2d');
        const grad = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
        grad.addColorStop(0, color);
        grad.addColorStop(0.4, color);
        grad.addColorStop(1, 'transparent');
        g.fillStyle = grad;
        g.fillRect(0, 0, size, size);
        sprites[key] = el;
        return el;
    }

    function seed() {
        if (type === 'embers') {
            const count = Math.round(Math.min(90, (w * h) / 24000) * intensity);
            particles = Array.from({ length: count }, () => ({
                x: rand(0, w), y: rand(0, h),
                r: rand(1.1, 3.2), vy: rand(8, 26),
                sway: rand(0.4, 1.2), phase: rand(0, Math.PI * 2),
                a: rand(0.25, 0.75),
            }));
        } else if (type === 'stars') {
            const count = Math.round(Math.min(160, (w * h) / 12000) * intensity);
            particles = Array.from({ length: count }, () => ({
                x: rand(0, w), y: rand(0, h), r: rand(0.4, 1.4),
                phase: rand(0, Math.PI * 2), speed: rand(0.3, 1.1),
                a: rand(0.25, 0.8),
            }));
        } else if (type === 'network') {
            const count = Math.round(Math.min(110, (w * h) / 14000) * intensity);
            particles = Array.from({ length: count }, () => ({
                x: rand(0, w), y: rand(0, h),
                vx: rand(-14, 14), vy: rand(-14, 14),
                r: rand(1, 2.2),
            }));
        } else if (type === 'flow') {
            const count = Math.round(Math.min(420, (w * h) / 4200) * intensity);
            particles = Array.from({ length: count }, spawnFlowParticle);
        } else if (type === 'warp') {
            const count = Math.round(Math.min(220, (w * h) / 9000) * intensity);
            particles = Array.from({ length: count }, () => ({
                x: rand(-1, 1), y: rand(-1, 1), z: rand(0.05, 1),
            }));
        } else if (type === 'bokeh') {
            const count = Math.round(Math.min(26, (w * h) / 60000) * intensity);
            particles = Array.from({ length: count }, () => ({
                x: rand(0, w), y: rand(0, h),
                r: rand(18, 54),
                vx: rand(-7, 7), vy: rand(-5, 5),
                a: rand(0.08, 0.2), phase: rand(0, Math.PI * 2),
            }));
        } else if (type === 'mesh') {
            seedMesh();
        }
    }

    // rasterise the Aegis mark offscreen, then sample it on a grid: each lit
    // cell becomes the resting position of one particle
    function buildMeshTargets() {
        const size = 320;
        const s = size / 512;
        const off = document.createElement('canvas');
        off.width = off.height = size;
        const g = off.getContext('2d');

        g.beginPath();
        g.moveTo(166 * s, 96 * s);
        g.lineTo(346 * s, 96 * s);
        g.quadraticCurveTo(406 * s, 96 * s, 406 * s, 156 * s);
        g.lineTo(406 * s, 268 * s);
        g.bezierCurveTo(406 * s, 350 * s, 336 * s, 396 * s, 256 * s, 436 * s);
        g.bezierCurveTo(176 * s, 396 * s, 106 * s, 350 * s, 106 * s, 268 * s);
        g.lineTo(106 * s, 156 * s);
        g.quadraticCurveTo(106 * s, 96 * s, 166 * s, 96 * s);
        g.closePath();
        g.fillStyle = '#fff';
        g.fill();

        // the A is carved out, same as the icon
        g.globalCompositeOperation = 'destination-out';
        g.lineCap = 'round';
        g.lineWidth = 38 * s;
        g.beginPath();
        g.moveTo(256 * s, 170 * s);
        g.lineTo(188 * s, 330 * s);
        g.stroke();
        g.beginPath();
        g.moveTo(256 * s, 170 * s);
        g.lineTo(324 * s, 330 * s);
        g.stroke();
        g.lineWidth = 30 * s;
        g.beginPath();
        g.moveTo(216 * s, 280 * s);
        g.lineTo(296 * s, 280 * s);
        g.stroke();

        const data = g.getImageData(0, 0, size, size).data;
        const step = 5;
        const points = [];
        for (let y = 0; y < size; y += step) {
            for (let x = 0; x < size; x += step) {
                if (data[(y * size + x) * 4 + 3] > 128) {
                    points.push({ x: x / size, y: y / size });
                }
            }
        }
        return points;
    }

    function seedMesh() {
        const points = buildMeshTargets();
        const scale = Math.min(w, h) * 0.68;
        const ox = (w - scale) / 2;
        const oy = (h - scale) / 2;
        const pitch = (scale / 320) * 5;

        particles = points.map((p) => {
            const tx = ox + p.x * scale;
            const ty = oy + p.y * scale;
            return {
                tx, ty,
                // start scattered so the mark assembles itself on entry
                x: tx + rand(-w * 0.45, w * 0.45),
                y: ty + rand(-h * 0.45, h * 0.45),
                vx: 0, vy: 0,
                s: Math.max(1.3, pitch * rand(0.3, 0.55)),
                a: rand(0.45, 1),
                ph: rand(0, Math.PI * 2),
            };
        });
    }

    function drawMesh(dt, t) {
        const color = cssVar('--effect-color', '#6ee7b7');
        const stiffness = 60;
        const damping = 12;
        const pushRadius = 150;

        ctx.fillStyle = color;
        for (const p of particles) {
            const wobble = Math.sin(t * 0.9 + p.ph) * 1.4;
            let ax = (p.tx + wobble - p.x) * stiffness;
            let ay = (p.ty + wobble * 0.6 - p.y) * stiffness;
            ax -= p.vx * damping;
            ay -= p.vy * damping;

            if (pointer.active) {
                const dx = p.x - pointer.x;
                const dy = p.y - pointer.y;
                const d2 = dx * dx + dy * dy;
                if (d2 < pushRadius * pushRadius && d2 > 1) {
                    const d = Math.sqrt(d2);
                    const force = (1 - d / pushRadius) * 2600;
                    ax += (dx / d) * force;
                    ay += (dy / d) * force;
                }
            }

            p.vx += ax * dt;
            p.vy += ay * dt;
            p.x += p.vx * dt;
            p.y += p.vy * dt;

            ctx.globalAlpha = p.a;
            ctx.fillRect(p.x, p.y, p.s, p.s);
        }
        ctx.globalAlpha = 1;
    }

    function drawEmbers(dt, t) {
        const sprite = makeSprite(64, cssVar('--effect-color', cssVar('--accent', '#ff7a3d')));
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

            if (p.y < -8) { p.y = h + 8; p.x = rand(0, w); }
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

    // drifting nodes wired to their neighbours, with the cursor pulling them in
    function drawNetwork(dt) {
        const color = cssVar('--effect-color', '#7dd3fc');
        const maxSpeed = 26;

        for (const p of particles) {
            p.x += p.vx * dt;
            p.y += p.vy * dt;
            if (p.x < 0) { p.x = 0; p.vx = Math.abs(p.vx); }
            else if (p.x > w) { p.x = w; p.vx = -Math.abs(p.vx); }
            if (p.y < 0) { p.y = 0; p.vy = Math.abs(p.vy); }
            else if (p.y > h) { p.y = h; p.vy = -Math.abs(p.vy); }

            if (pointer.active) {
                const dx = pointer.x - p.x;
                const dy = pointer.y - p.y;
                const d2 = dx * dx + dy * dy;
                if (d2 < 220 * 220 && d2 > 1) {
                    const d = Math.sqrt(d2);
                    p.vx += (dx / d) * 8 * dt;
                    p.vy += (dy / d) * 8 * dt;
                }
            }

            const speed = Math.hypot(p.vx, p.vy);
            if (speed > maxSpeed) {
                p.vx = (p.vx / speed) * maxSpeed;
                p.vy = (p.vy / speed) * maxSpeed;
            }
        }

        const link = 130;
        ctx.lineWidth = 1;
        ctx.strokeStyle = color;
        for (let i = 0; i < particles.length; i++) {
            const a = particles[i];
            for (let j = i + 1; j < particles.length; j++) {
                const b = particles[j];
                const dx = a.x - b.x;
                const dy = a.y - b.y;
                const d2 = dx * dx + dy * dy;
                if (d2 > link * link) continue;
                ctx.globalAlpha = (1 - Math.sqrt(d2) / link) * 0.35;
                ctx.beginPath();
                ctx.moveTo(a.x, a.y);
                ctx.lineTo(b.x, b.y);
                ctx.stroke();
            }
        }

        ctx.globalAlpha = 0.9;
        ctx.fillStyle = color;
        for (const p of particles) {
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
            ctx.fill();
        }
        ctx.globalAlpha = 1;
    }

    function spawnFlowParticle() {
        return {
            x: rand(0, w), y: rand(0, h),
            life: rand(2.5, 7), age: 0,
            warm: Math.random() > 0.5,
        };
    }

    function flowAngle(x, y, t) {
        // three cheap sines make a smooth, non-repeating stream field
        return Math.sin(x * 0.0025 + t * 0.15) * 1.6
             + Math.cos(y * 0.003 - t * 0.11) * 1.6
             + Math.sin((x + y) * 0.0012) * 1.2;
    }

    function drawFlow(dt, t) {
        const cool = cssVar('--effect-color', '#c084fc');
        const warm = cssVar('--accent-secondary', '#f472b6');
        ctx.lineWidth = 1.1;

        for (const p of particles) {
            const angle = flowAngle(p.x, p.y, t);
            let vx = Math.cos(angle) * 42;
            let vy = Math.sin(angle) * 42;

            if (pointer.active) {
                const dx = p.x - pointer.x;
                const dy = p.y - pointer.y;
                const d = Math.hypot(dx, dy);
                if (d < 170 && d > 1) {
                    const f = (170 - d) / 170;
                    // swirl around the cursor instead of pushing straight out
                    vx += (-dy / d) * 110 * f;
                    vy += (dx / d) * 110 * f;
                }
            }

            const nx = p.x + vx * dt;
            const ny = p.y + vy * dt;
            ctx.strokeStyle = p.warm ? warm : cool;
            ctx.globalAlpha = 0.4;
            ctx.beginPath();
            ctx.moveTo(p.x, p.y);
            ctx.lineTo(nx, ny);
            ctx.stroke();

            p.x = nx;
            p.y = ny;
            p.age += dt;
            if (p.age > p.life || p.x < -20 || p.x > w + 20 || p.y < -20 || p.y > h + 20) {
                Object.assign(p, spawnFlowParticle());
            }
        }
        ctx.globalAlpha = 1;
    }

    // hyperspace: stars dive toward the viewer, the cursor is the vanishing point
    function drawWarp(dt) {
        const cx = pointer.active ? pointer.x : w / 2;
        const cy = pointer.active ? pointer.y : h / 2;
        const speed = 0.3;

        ctx.strokeStyle = cssVar('--effect-color', '#dbeafe');
        ctx.lineWidth = 1.2;

        for (const p of particles) {
            const prevZ = p.z;
            p.z -= speed * dt;
            if (p.z <= 0.03) {
                p.x = rand(-1, 1);
                p.y = rand(-1, 1);
                p.z = 1;
                continue;
            }
            const k = 1 / p.z;
            const pk = 1 / prevZ;
            const x1 = cx + p.x * k * 120;
            const y1 = cy + p.y * k * 120;
            const x0 = cx + p.x * pk * 120;
            const y0 = cy + p.y * pk * 120;
            ctx.globalAlpha = Math.min(1, (1 - p.z) * 0.9);
            ctx.beginPath();
            ctx.moveTo(x0, y0);
            ctx.lineTo(x1, y1);
            ctx.stroke();
        }
        ctx.globalAlpha = 1;
    }

    function drawBokeh(dt, t) {
        const sprite = makeSprite(128, cssVar('--effect-color', cssVar('--accent', '#f0abfc')));
        const px = pointer.active ? (pointer.x - w / 2) * 0.03 : 0;
        const py = pointer.active ? (pointer.y - h / 2) * 0.03 : 0;

        ctx.globalCompositeOperation = 'lighter';
        for (const p of particles) {
            p.x += p.vx * dt;
            p.y += p.vy * dt;
            if (p.x < -p.r) p.x = w + p.r;
            else if (p.x > w + p.r) p.x = -p.r;
            if (p.y < -p.r) p.y = h + p.r;
            else if (p.y > h + p.r) p.y = -p.r;

            const bob = Math.sin(t * 0.4 + p.phase) * 0.5 + 0.5;
            ctx.globalAlpha = p.a * (0.6 + 0.4 * bob);
            ctx.drawImage(sprite, p.x - p.r + px, p.y - p.r + py, p.r * 2, p.r * 2);
        }
        ctx.globalAlpha = 1;
        ctx.globalCompositeOperation = 'source-over';
    }

    function frame(now) {
        raf = 0;
        if (!ctx || !type) return;
        const dt = Math.min(0.05, (now - last) / 1000 || 0.016);
        last = now;
        const t = now / 1000;

        if (trailAlpha > 0) {
            // fade the previous frame toward transparent: motion trails that
            // still let the theme background show through
            ctx.globalCompositeOperation = 'destination-out';
            ctx.fillStyle = `rgba(0,0,0,${trailAlpha})`;
            ctx.fillRect(0, 0, w, h);
            ctx.globalCompositeOperation = 'source-over';
        } else {
            ctx.clearRect(0, 0, w, h);
        }

        if (type === 'embers') drawEmbers(dt, t);
        else if (type === 'stars') drawStars(t);
        else if (type === 'network') drawNetwork(dt);
        else if (type === 'flow') drawFlow(dt, t);
        else if (type === 'warp') drawWarp(dt);
        else if (type === 'bokeh') drawBokeh(dt, t);
        else if (type === 'mesh') drawMesh(dt, t);

        raf = requestAnimationFrame(frame);
    }

    function start() {
        ensureCanvas();
        resize();
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
        const nextType = effects && effects.type ? String(effects.type) : null;
        const nextIntensity = effects && effects.intensity != null ? (Number(effects.intensity) || 1) : 1;
        const nextTrail = effects && effects.trail != null ? Math.max(0, Math.min(0.5, Number(effects.trail))) : 0;

        if (!nextType || !CANVAS_TYPES.has(nextType)) {
            // includes "aurora", which is pure CSS
            stop();
            type = null;
            return;
        }
        if (nextType === type && nextIntensity === intensity && nextTrail === trailAlpha) return;

        stop();
        type = nextType;
        intensity = nextIntensity;
        trailAlpha = nextTrail;
        if (!reduced.matches && !document.hidden) start();
    }

    window.addEventListener('theme-effect-changed', (event) => setEffect(event.detail));
    // a theme swap changes the accent colours: rebuild sprites and particles
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
            trail: Number(root.dataset.themeEffectTrail || 0),
        });
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
    else boot();
})();
