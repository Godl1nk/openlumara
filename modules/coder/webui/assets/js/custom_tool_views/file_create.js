/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-25) harness:openlumara
   coder module view: coder_file_create shows the new file's content,
   highlighted, streamed live from the args.
   codeLinesHtml lives in the webui's renderers/custom_tool_views/shared.js,
   langForPath in this folder's shared.js; markup in this module's
   templates/chat/tool_displays.html (tool_views slot); styling in this
   folder's shared.css. */

document.addEventListener('alpine:init', () => {
    // coder file creates: the new file's content, highlighted, streamed live
    registerToolDisplay({
        match: /^coder_file_create$/,
        view: 'file-create'
        // the "N lines" header hint is backend-owned now
        // (_metadata.result_summary via coder's on_tool_summary)
    });
});
