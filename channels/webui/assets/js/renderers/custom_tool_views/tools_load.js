// -- AI GENERATED CODE (qwen3.8-flash-next) :: (2026-10-25) harness:openlumara
// tools_load view: the core meta-tool that fetches tool schemas stays a
// webui-owned view (it belongs to the framework, not to any module).
// Shared memo/highlight machinery lives in ./shared.js; markup in
// templates/chat/tool_displays.html; styling in css/chat/custom_tool_views.css.

// the args' module_names list is the live preview while streaming; the
// response carries {tools: [{name, description, parameters}], not_found,
// disabled}. the full parameters are way too big for a card, so the view
// summarises: one line per tool (name + dimmed description), grouped per
// requested module.
function toolLoadModules(args) {
    return Array.isArray(args.module_names) ? args.module_names : [];
}

function toolLoadGroups(tool, cacheKey) {
    const resp = toolResponse(tool);
    const tools = Array.isArray(resp?.tools) ? resp.tools : [];
    const groups = [];
    const claimed = new Set();
    // group by the REQUESTED module names (module names may contain
    // underscores, so prefix-matching on the request beats name.split):
    // a tool belongs to the module whose name it starts with + '_'.
    for (const mod of toolLoadModules(toolArgs(tool, cacheKey))) {
        const prefix = String(mod).toLowerCase() + '_';
        const own = tools.filter(t =>
            typeof t?.name === 'string' &&
            t.name.toLowerCase().startsWith(prefix) && !claimed.has(t.name));
        own.forEach(t => claimed.add(t.name));
        if (own.length) groups.push({module: String(mod), tools: own});
    }
    const rest = tools.filter(t => !claimed.has(t?.name));
    if (rest.length) groups.push({module: 'tools', tools: rest});
    return {
        running: !resp,
        groups,
        notFound: Array.isArray(resp?.not_found) ? resp.not_found : [],
        enabled: Array.isArray(resp?.enabled_modules) ? resp.enabled_modules : [],
        disabled: Array.isArray(resp?.disabled) ? resp.disabled : [],
    };
}

document.addEventListener('alpine:init', () => {
    // tools_load: which modules' tools just got loaded
    // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
    // summary dropped: the module chips in the view tell the whole story,
    // repeating them in the collapsed header was redundant
    registerToolDisplay({
        match: /^tools_load$/,
        view: 'tools-load'
    });
});
