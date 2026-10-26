/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-25) harness:openlumara
   web search module view: web_search_* results render as titled link cards.
   markup in this module's templates/chat/tool_displays.html (tool_views
   slot); styling in this folder's web_search.css. */

// flatten a web_search response into display cards: [{ title, url, thumb,
// snippet, note }]. response shape: { status, content: [ wrapped,
// instruction ] } with the results living in wrapped.web_content. url key
// differs per kind (href for text, url/image for the rest), snippet
// likewise (body/description/info). only http(s) urls are passed through;
// anything else renders as plain text.
// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
// results rejected by the module's url policy arrive as [REDACTED]
// placeholders plus a note field; carry it through so the card can show
// WHY it's empty instead of a bare untitled shell.
function searchResults(response) {
    const wrapped = response?.content?.find?.(c => c && typeof c === 'object' && c.web_content);
    const items = Array.isArray(wrapped?.web_content) ? wrapped.web_content : [];
    const safeUrl = u => (typeof u === 'string' && /^https?:\/\//i.test(u)) ? u : '';
    return items.map(res => {
        const note = typeof res.note === 'string' ? res.note : '';
        return {
            title: res.title && res.title !== '[REDACTED]' ? res.title : (note ? '' : '(untitled)'),
            url: safeUrl(res.href || res.url || res.image),
            thumb: safeUrl(res.thumbnail),
            snippet: res.body && res.body !== '[REDACTED]'
                ? res.body
                : (res.description || res.info || ''),
            note,
        };
    });
}

document.addEventListener('alpine:init', () => {
    // web searches: render results as titled link cards
    registerToolDisplay({
        match: /^web_search_(text|images|news|videos|books)$/,
        view: 'web-search'
        // the "n results" header hint is backend-owned now
        // (_metadata.result_summary via web_search's on_tool_summary)
    });
});
