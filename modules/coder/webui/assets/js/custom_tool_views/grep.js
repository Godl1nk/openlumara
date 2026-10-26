/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-25) harness:openlumara
   coder module view: coder_folder_grep / coder_file_grep render as
   file-grouped match lists with line numbers + context.
   markup in this module's templates/chat/tool_displays.html (tool_views
   slot); styling in this folder's grep.css (the running one-liner shares
   shared.css). */

// normalize the grep response into [{ file, matches }]. content is a flat
// array of match dicts, or { matches, note } when the max_matches cap hit.
// folder_grep matches carry a per-match file; file_grep matches don't, so
// those group under the file_path argument instead.
function grepGroups(response, args) {
    if (!response || response.status !== 'success') return [];
    const c = response.content;
    const items = Array.isArray(c) ? c : (Array.isArray(c?.matches) ? c.matches : []);
    const fallbackFile = args?.file_path ?? args?.sub_path ?? 'matches';
    const groups = new Map();
    for (const m of items) {
        const file = m.file ?? fallbackFile;
        if (!groups.has(file)) groups.set(file, []);
        groups.get(file).push(m);
    }
    return [...groups.entries()].map(([file, matches]) => ({ file, matches }));
}

// flatten one file's matches into display rows: dimmed context_before, the
// highlighted match line, dimmed context_after. line numbers only on the
// match itself (context lines get a blank gutter).
function grepRows(matches) {
    const rows = [];
    for (const m of matches ?? []) {
        for (const line of m.context_before ?? [])
            rows.push({ num: '', text: line, kind: 'ctx' });
        rows.push({ num: m.line_num, text: m.line, kind: 'hit' });
        for (const line of m.context_after ?? [])
            rows.push({ num: '', text: line, kind: 'ctx' });
    }
    return rows;
}

document.addEventListener('alpine:init', () => {
    // grep calls: file-grouped match lists with line numbers + context
    registerToolDisplay({
        match: /^coder_(folder|file)_grep$/,
        view: 'grep'
        // the "n matches · m files" header hint is backend-owned now
        // (_metadata.result_summary via coder's on_tool_summary)
    });
});
