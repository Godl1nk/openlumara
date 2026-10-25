# OpenLumara webui themes

Each `.json` file in this folder is one theme family. The filename (minus `.json`) is the family name shown in **Settings → Appearance → Theme**. `base.json` is special — it provides the full set of default CSS variables that every theme can override.

## Format

```json
{
  "dark":  { "--bg-primary": "#0a0712", "--accent": "#b388ff" },
  "light": { "--bg-primary": "#f7f3fc", "--accent": "#7c4dcc" }
}
```

- Only `dark` and `light` are needed; whichever mode a theme lacks falls back to the other.
- Keys inside `dark`/`light` are applied as CSS custom properties on `<html>`.

## Sidecar CSS (theme effects)

Want more than color variables? Drop a `.css` file **with the same name as your theme JSON** next to it:

```
themes/
  cute-sakura.json
  cute-sakura.css   ← loaded automatically when cute-sakura is active
```

The theme engine (`assets/js/stores/theming.js`) loads it as a stylesheet when the family becomes active and removes it again when you switch away. No declaration in the JSON needed — the file's existence *is* the declaration.

**CSS only.** JavaScript sidecars are deliberately not supported: theme code runs in the page context with full access to everything, which is a security risk we don't take. Pure CSS can do far more than you'd think (animated gradients, pseudo-element effects, box-shadow particle fields, backdrop blur...).

Want real JS effects (canvas particles, per-element animation)? Ship them as a **user module with a webui extension** instead (`<module>/webui/assets/js/` is auto-injected, and the `theme-changed` window event lets the effect activate only while your theme is active). See `user_modules/sakura_effects/` for a full working example: falling petals + sparkles tied to the `cute-sakura` theme. The difference in trust model: modules are code *you* installed and enabled, themes are data anyone can share.

Tips for theme authors:
- The sidecar loads after every core stylesheet, so it wins on specificity ties (`!important` still helps for inline styles).
- For ambient background layers, use `position: fixed; pointer-events: none;` with a negative `z-index` so they sit behind the app content.
- Respect `@media (prefers-reduced-motion: reduce)` — disable animations for users who ask you to.
- Keep it reasonably light; this CSS is on screen all day.

## Animated effects

A theme family can ask the core canvas layer (`assets/js/effects/theme_effects.js`) to
animate behind — or above — the app. Declare it in the theme JSON:

```json
{
  "effects": { "type": "petals", "intensity": 1, "trail": 0.08, "overlay": true },
  "dark": { "--bg-primary": "rgba(28, 20, 16, 0.62)" }
}
```

| key | meaning |
| --- | --- |
| `type` | `petals`, `flow`, `network`, `mesh`, `embers`, `stars`, `bokeh`, `warp`, or `aurora` |
| `intensity` | particle-count multiplier (default `1`) |
| `trail` | `0`–`0.5`: fade the previous frame instead of clearing it, giving motion trails |
| `overlay` | draw above the page (`z-index: 1`) instead of behind it |

The engine already pauses while the tab is hidden, stops when the theme changes, scales
particle counts by viewport area and disables itself when the user prefers reduced
motion. `aurora` is CSS-only, so no canvas is created for it.

The canvas sits at `z-index: -1` by default, so the theme's surfaces need to be slightly
translucent (`rgba(...)` backgrounds) for the effect to show through. Themes with
opaque surfaces — like the washi paper in `effects-hanami` — set `"overlay": true` so
the effect floats above the UI instead.

Shipped effect themes:

- `effects-hanami` — falling petals over warm paper (overlay)
- `effects-ink` — ink blooms and flowing tendrils on white
- `effects-wire` — constellation mesh with pulses on black

Effects are data, not code: the theme JSON only names an effect and its intensity, so a
shared theme file still cannot run JavaScript.
