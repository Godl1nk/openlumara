# Aegis

Aegis is a self-hosted AI agent workspace: a modular, token-efficient Python agent
core with a fast Alpine.js WebUI, a CLI, and chat-channel integrations. It talks to any OpenAI-compatible backend — local `llamacpp`,
`llama-swap`, `ollama`, `vllm`, or a cloud provider — and keeps the system prompt
small enough to leave most of the context for actual work.

**Aegis is a fork of [OpenLumara](https://github.com/Rose22/openlumara) by Rose22.**
The framework, channels and the bulk of the code are upstream work; this fork focuses
on the WebUI experience, image tooling, and reliability. Upstream remains the source
of truth for the framework itself.

> Internal identifiers intentionally keep the upstream name — the `openlumara/`
> checkout folder, config keys, module names and the `/api/ext/...` routes. Only
> user-facing branding says Aegis, so existing installs, configs and scripts keep
> working unchanged.

## What this fork adds

### Image generation and editing

- Real generation through any OpenAI-compatible `/images/generations` endpoint, with
  per-request model selection and an offline mock backend for testing.
- Edited images return a ready-to-use `url` and `markdown`, so results render in chat
  instead of a filesystem path.
- `/api/ext/image_tools/view` streams the actual bytes — generated and edited images
  display inline and open at full size.
- Generation runs in an animated card: a themed placeholder with a drifting glow while
  the request runs, then the finished image with its prompt. Steps holding an image
  result stay expanded, so the picture is visible without opening the process block.
- Optional approval gate before generating or editing, answered either from the inline
  card or with a normal chat message ("yes, approve the resize" works).
- Separate default choices for image generation and image editing; editing can follow
  generation automatically or use a different marked image model.

### Model management

- One API page for providers and models. The picture icon marks image capability.
- Default chat, image-generation, and image-editing models are selected below the model
  list and reflected by badges and borders on the rows.
- Chat-only settings live on each chat model: context, temperature, thinking effort,
  output limit, message-history limit, history trim block, developer role, and custom
  request fields. “Default” sends no override so the host server decides.
- Image-marked models hide chat-only settings and cannot also be the default chat model.

### Human-in-the-loop questions

- `ask_user` renders as an inline card above the composer — question, option buttons and
  a free-text field — instead of a modal window.
- The countdown is derived from a server deadline, so a background tab can't show stale
  time; the tab resyncs as soon as it becomes visible.
- Waiting for an approval no longer reports a stuck `0% ETA`; with no progress data the
  indicator reads "Waiting for model…" and runs indeterminate.

### Live telemetry and controls

- **tok/s readout** in the header next to the model picker. It uses the server's own
  `timings` when the backend provides them (llama.cpp and compatible servers) and falls
  back to an estimate over streamed text, which also covers vLLM and anything else.
  The last value stays visible between turns.
- **Reasoning effort picker** next to the model selector, editing the active model's
  thinking effort (Default / None / Low / Medium / High / xhigh / Max) with the global
  preset as a fallback.

### Themes and animated effects

Three effect themes ship with the fork, in **Settings → Appearance → Effects**:

| Theme | Motion |
|---|---|
| **Hanami** | Warm washi paper with falling cherry petals that scatter away from the cursor |
| **Ink** | White paper with ink blooms and flowing tendrils; the cursor draws a vortex |
| **Wire** | Black room with a constellation mesh — depth, energy pulses along the links, and ripples thrown out by the cursor |

Effect themes declare their animation in the theme JSON and are rendered on a single
canvas layer by `assets/js/effects/theme_effects.js`. Everything pauses when the tab is
hidden, scales its particle count with the viewport, and is disabled entirely under
`prefers-reduced-motion`. See [themes/README.md](channels/webui/themes/README.md) for
the schema.

### Reliability fixes

- Interrupted turns no longer leave an assistant `tool_calls` entry without a matching
  tool result; missing results are filled in before the context is sent, so one canceled
  call can't poison the rest of the conversation.
- llama.cpp router load banners ("llama-swap loading model…") are filtered out of the
  stream, and an empty completion is retried once the model is loaded.
- Reasoning and content tokens in the same SSE chunk are both emitted instead of one
  overwriting the other.
- New settings defined in a module schema appear in the settings UI without editing the
  config by hand.
- Static assets carry a per-deploy version token and the theme list is never cached, so
  updates actually reach the browser.
- `/new` no longer leaves a dangling message in the chat it switches away from, and a
  saved theme that was removed falls back to the default instead of bare colours.

## Install

```bash
git clone https://github.com/Godl1nk/openlumara
cd openlumara
./run.sh          # or run.bat on Windows
```

Open the URL it prints, then set up your API connection in the settings panel (gear
icon) and save.

## Updating

```bash
./update.sh       # or update.bat on Windows
```

The update script pulls the current branch and keeps the virtualenv in sync. If you run
Aegis on a server, restart it after updating; the deployment used for development runs
it inside a `screen` session with `./venv/bin/python main.py`.

Screenshots in this README are intentionally omitted — the WebUI changes often enough
that static images go stale; the running instance is the reference.

## License

GPLv3, inherited from OpenLumara. See [LICENSE](LICENSE).

Upstream project: <https://github.com/Rose22/openlumara>
