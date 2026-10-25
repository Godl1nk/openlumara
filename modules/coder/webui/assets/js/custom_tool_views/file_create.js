/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-25) harness:openlumara
   coder module view: coder_file_create shows the new file's content,
   highlighted, streamed live from the args.
   codeLinesHtml lives in the webui's renderers/custom_tool_views/shared.js,
   langForPath in this folder's shared.js; markup in the webui's
   tool_displays.html; styling in css/chat/custom_tool_views.css. */

document.addEventListener('alpine:init', () => {
    // coder file creates: the new file's content, highlighted, streamed live
    registerToolDisplay({
        match: /^coder_file_create$/,
        view: 'file-create',
        summary: (res, tool, cacheKey) => {
            if (res?.status !== 'success') return '';
            const content = toolArgs(tool, cacheKey).content;
            if (!content) return '';
            const n = content.replace(/\n$/, '').split('\n').length;
            return `${n} line${n === 1 ? '' : 's'}`;
        }
    });
});
