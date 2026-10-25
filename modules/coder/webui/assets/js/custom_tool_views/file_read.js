/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-25) harness:openlumara
   coder module view: coder_file_read renders as a highlighted code block.
   the block machinery (codeLinesHtml) lives in the webui's
   renderers/custom_tool_views/shared.js, langForPath in this folder's
   shared.js; markup in the webui's tool_displays.html; styling in
   css/chat/custom_tool_views.css. */

document.addEventListener('alpine:init', () => {
    // coder file reads: highlighted code block
    registerToolDisplay({
        match: /^coder_file_read$/,
        view: 'file-read',
        summary: res => {
            if (!res || res.status === 'error' || typeof res.content !== 'string') return '';
            const n = res.content.split('\n').length;
            return `${n} line${n === 1 ? '' : 's'}`;
        }
    });
});
