// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-18)
// tool display CORE: the registry + generic template helpers that let
// specific tool calls render from an inline markup view instead of the
// default arg rows. the view markup branches live in the webui's
// templates/chat/tool_displays.html (core views) plus each module's own
// templates/chat/tool_displays.html, stitched in through the file's
// tool_views extension slot.
// NO html strings - the registry only matches and names views; all markup
// lives in the template files.
//
// THE VIEWS THEMSELVES (per-tool helpers + registry entries) live in
// js/renderers/custom_tool_views/ + the per-module
    // webui/assets/js/custom_tool_views/ folders - this file is system only, so the
// whole view collection can grow/ship separately (and eventually be
// replaced/extended by plugins).
//
// registry entry shape (registered by the views file):
//   match:   RegExp tested against the tool function name
//   view:    name of the template branch to render; the branch lives in
//            the webui's or a module's chat/tool_displays.html (tool_views slot)

const TOOL_DISPLAYS = [];

function registerToolDisplay(entry) {
    TOOL_DISPLAYS.push(entry);
}

function toolDisplayFor(name) {
    if (!name) return null;
    return TOOL_DISPLAYS.find(d => d.match.test(name)) ?? null;
}

// -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-21) harness:openlumara
// the name a call should display as: calls proxied through tools_call are
// unwrapped by core/turns.py into _metadata.display_name (and their inner
// args into _metadata.args_parsed), so bridged calls render exactly like
// native ones. falls back to the raw function name for everything else.
function toolDisplayName(tool) {
    return tool?._metadata?.display_name || tool?.function?.name || '';
}

// which template branch (if any) renders this call's body; null = default
function toolDisplayView(tool) {
    return toolDisplayFor(toolDisplayName(tool))?.view ?? null;
}

// -- AI GENERATED CODE (qwen3.8-flash-next) :: (2026-10-25) harness:openlumara
// one-line result hint for the completed tool call header. fully
// backend-owned now: core/turns.py asks the owning module's
// on_tool_summary(name, args, response) hook and stamps the ready-made line
// as _metadata.result_summary (live stream AND history reloads). the JS
// summary callbacks are gone - the registry only matches and names views,
// and the frontend is a pure display sink. empty = show nothing.
function toolCallResultSummary(tool) {
    return tool?._metadata?.result_summary || '';
}

// -- generic template helpers ----------------------------------------------
// (view-specific data helpers belong in the per-module
// custom_tool_views/ folders, not here)

// parsed (possibly PARTIAL, mid-stream) arguments for a claimed tool
// call, for use inside the view templates. {} until anything parses.
// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
// arguments are parsed backend-side now (core/turns.py stamps a
// monotonic args_parsed object onto every tool call, in history and
// while streaming); the frontend's partial-JSON parser is gone.
// cacheKey is kept in the signature so view call-sites don't churn.
function toolArgs(tool, cacheKey) {
    // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-13)
    // args_parsed lives under the tool call's _metadata key
    const a = tool?._metadata?.args_parsed;
    if (a !== null && typeof a === 'object') return a;
    return {};
}

// parsed tool response object, or null while it's absent/incomplete.
// for use inside the view templates.
function toolResponse(tool) {
    try {
        // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-13)
        // response lives under the tool call's _metadata key
        const p = JSON.parse(tool._metadata?.response);
        if (p !== null && typeof p === 'object') return p;
    } catch { /* response not (fully) here yet */ }
    return null;
}
