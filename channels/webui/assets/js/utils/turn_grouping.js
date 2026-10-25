/*
 * -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-25) harness:openlumara
 * the step-based stream (core/turns.py) now delivers the live turn in
 * exactly the history shape: step upserts + authoritative final-bubble
 * snapshots, so ALL chain/step folding lives in the core and this file is
 * display logic only.
 *
 * what used to live here (streamSteps, streamTurnSplit, resplitHistoryTurn,
 * stepIsThinkingLive) all moved backend-side with the 2026-10-25 step
 * stream refactor.
 *
 * what stays: how MUCH of a thought to show in a step header. the backend
 * always ships reasoning in FULL - previewing it is per-channel display
 * logic and belongs to the webui.
 */

// header preview of a thought: the LAST sentence of the whole reasoning
// (whitespace collapsed across lines), then the classic truncation: cut
// at the last sentence terminator that still fits within max chars,
// otherwise a clean word cut with an ellipsis. no mid-word pixel
// guillotines in the chain. while streaming this tracks the thought as
// it unfolds, since the newest sentence is always the live one.
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
