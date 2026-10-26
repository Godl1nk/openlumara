const TOOL_DISPLAYS = [];

function registerToolDisplay(entry) {
    TOOL_DISPLAYS.push(entry);
}

function toolDisplayFor(name) {
    if (!name) return null;
    return TOOL_DISPLAYS.find(d => d.match.test(name)) ?? null;
}

// the name a call should display as
function toolDisplayName(tool) {
    return tool?._metadata?.display_name || tool?.function?.name || '';
}

// which template branch (if any) renders this call's body; null = default
function toolDisplayView(tool) {
    return toolDisplayFor(toolDisplayName(tool))?.view ?? null;
}

function toolCallResultSummary(tool) {
    return tool?._metadata?.result_summary || '';
}

// -- generic template helpers ----------------------------------------------
function toolArgs(tool, cacheKey) {
    // args_parsed lives under the tool call's _metadata key
    const a = tool?._metadata?.args_parsed;
    if (a !== null && typeof a === 'object') return a;
    return {};
}

// parsed tool response object, or null while it's absent/incomplete.
// for use inside the view templates.
function toolResponse(tool) {
    try {
        // response lives under the tool call's _metadata key
        const p = JSON.parse(tool._metadata?.response);
        if (p !== null && typeof p === 'object') return p;
    } catch { /* response not (fully) here yet */ }
    return null;
}
