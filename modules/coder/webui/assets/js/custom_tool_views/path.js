/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-25) harness:openlumara
   coder module view: the sandbox/path one-liner for coder_glob (plus its
   file list) and the running preview for coder_file_move / coder_file_delete
   / coder_folder_delete.
   markup in this module's templates/chat/tool_displays.html (tool_views
   slot); styling in this folder's path.css (the running one-liner shares
   shared.css). */

// running (no response yet) preview labels for the generic coder-path view:
// "moving \u00b7 dev: foo/bar.py". path picks whichever arg the tool uses.
const CODER_RUNNING_LABELS = {
    coder_glob: 'listing',
    coder_file_move: 'moving',
    coder_file_delete: 'deleting',
    coder_folder_delete: 'deleting folder',
};

// glob response -> plain list of file paths (content is a list or
// { results, truncated, note } when the result cap hit).
function globFiles(response) {
    if (!response || response.status !== 'success') return [];
    const c = response.content;
    const items = Array.isArray(c) ? c : (Array.isArray(c?.results) ? c.results : []);
    return items.filter(f => typeof f === 'string');
}

function coderRunningInfo(tool, cacheKey) {
    const args = toolArgs(tool, cacheKey);
    const path = args.path ?? args.orig_path ?? args.sub_path ?? '';
    // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
    // moves stream a destination too: surface it so the running one-liner
    // reads "moving \u00b7 dev: a.py -> b.py" instead of hiding where it goes
    return {
        label: CODER_RUNNING_LABELS[toolDisplayName(tool)] ?? 'in',
        sandbox: args.sandbox ?? '',
        path,
        out: args.target_path ?? '',
    };
}

document.addEventListener('alpine:init', () => {
    // coder glob: file list + count (claiming it now so the running
    // sandbox/path one-liner shows too; the result rows stay default)
    registerToolDisplay({
        match: /^coder_glob$/,
        view: 'coder-path'
        // the "n files" header hint is backend-owned now
        // (_metadata.result_summary via coder's _tool_summary)
    });

    // coder move/delete/folder_delete: running sandbox/path one-liner
    registerToolDisplay({
        match: /^coder_(file_move|file_delete|folder_delete)$/,
        view: 'coder-path'
    });
});
