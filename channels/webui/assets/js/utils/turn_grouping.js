function thoughtSnippet(text, max) {
    const limit = max || 80;
    const t = (text || '').replace(/\s+/g, ' ').trim();
    if (!t) return '';
    // sentence = run of text up to a terminator followed by whitespace
    // (or end of text); the last split piece is the final sentence
    const parts = t.split(/(?<=[.!?\u2026])\s+/);
    const s = parts[parts.length - 1].trim();
    if (s.length <= limit) return s;
    const win = s.slice(0, limit);
    // greedy: matches up through the LAST sentence end inside the window
    const term = win.match(/^[\s\S]*[.!?\u2026](?=\s|$)/);
    if (term && term[0].length >= 12) return term[0].trim();
    const sp = win.lastIndexOf(' ');
    return (sp > 20 ? win.slice(0, sp) : win.slice(0, limit - 1)).replace(/\s+$/, '') + '\u2026';
}