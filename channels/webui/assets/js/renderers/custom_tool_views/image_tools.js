// image generation/editing tool cards. markup lives in chat/tool_displays.html,
// styling in chat/custom_tool_views.css.
document.addEventListener('alpine:init', () => {
    registerToolDisplay({
        match: /^image_tools_(generate|resize|crop|rotate|flip|apply_filter|add_text|convert_format)$/,
        view: 'image-result',
        summary: res => res?.content?.filename || ''
    });
});

const IMAGE_TOOL_ACTION = /^(tools_)?(generate|resize|crop|rotate|flip|apply_filter|add_text|convert_format)$/;

// steps start expanded when they contain an image so the picture is visible
function stepHasImageResult(step) {
    for (const group of (step?.modules ?? [])) {
        if (!['image', 'image_tools'].includes(String(group?.module || '').toLowerCase())) continue;
        for (const action of (group?.actions ?? [])) {
            if (IMAGE_TOOL_ACTION.test(action?.name || '')) return true;
        }
    }
    return false;
}

function turnHasImageResult(turn) {
    if ((turn?.steps ?? []).some(stepHasImageResult)) return true;
    for (const segment of (turn?.messages ?? [])) {
        for (const tool of (segment?.tool_calls ?? [])) {
            if (toolDisplayView(tool) === 'image-result') return true;
        }
    }
    return false;
}
