/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-25) harness:openlumara
   coder module view: shows a coder_file_edit change as a diff (unified +
   side-by-side), live while the args stream.
   shared machinery (streamMemo) lives in the webui's
   renderers/custom_tool_views/shared.js; langForPath + coderFooterText in
   this folder's shared.js; markup in the webui's tool_displays.html; styling
   in css/chat/custom_tool_views.css. */

// generic helper: true line diff (LCS) between two code strings.
// common lines render as context, changed lines as -/+; long unchanged
// stretches collapse to a '..' marker with a couple context lines kept.
// works on partial (streaming) inputs too - it just re-diffs as it grows.
function diffLines(aText, bText) {
    const a = (aText || '').replace(/\n$/, '').split('\n');
    const b = (bText || '').replace(/\n$/, '').split('\n');
    if (a.length === 1 && a[0] === '') a.pop();
    if (b.length === 1 && b[0] === '') b.pop();

    // LCS table (classic dp). bail to naive mode for huge inputs.
    const n = a.length, m = b.length;
    if (n * m > 250000) return [...a.map(t => ['-', t]), ...b.map(t => ['+', t])];

    const dp = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
    for (let i = n - 1; i >= 0; i--)
        for (let j = m - 1; j >= 0; j--)
            dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);

    const out = [];
    let i = 0, j = 0;
    while (i < n && j < m) {
        if (a[i] === b[j]) { out.push([' ', a[i]]); i++; j++; }
        else if (dp[i + 1][j] >= dp[i][j + 1]) { out.push(['-', a[i]]); i++; }
        else { out.push(['+', b[j]]); j++; }
    }
    while (i < n) out.push(['-', a[i++]]);
    while (j < m) out.push(['+', b[j++]]);
    return out;
}

function collapseContext(rows, keep) {
    // keep `keep` context lines around changes, collapse the rest
    const out = [];
    let run = [];
    const flush = () => {
        if (run.length > keep * 2 + 1) {
            out.push(...run.slice(0, keep));
            out.push(['..', `${run.length - keep * 2} unchanged`]);
            out.push(...run.slice(-keep));
        } else out.push(...run);
        run = [];
    };
    for (const row of rows) {
        if (row[0] === ' ') run.push(row);
        else { flush(); out.push(row); }
    }
    flush();
    return out;
}

// per-line highlighting for diff rows. lines are highlighted in ISOLATION
// (the diff only shows excerpts, so whole-file highlighting is impossible):
// known languages only - per-line auto-detect would guess wildly. tiny
// cache: diffs re-run on every streamed chunk, and context lines mostly
// repeat between runs.
const _diffLineCache = new Map();
function highlightDiffLine(text, lang) {
    if (!text) return '';
    if (!lang || typeof hljs === 'undefined' || !hljs.getLanguage(lang))
        return escapeHtml(text);
    const key = lang + '\u0000' + text;
    let html = _diffLineCache.get(key);
    if (html === undefined) {
        try {
            html = hljs.highlight(text, { language: lang, ignoreIllegals: true }).value;
        } catch {
            html = escapeHtml(text);
        }
        if (_diffLineCache.size > 2000) _diffLineCache.clear();
        _diffLineCache.set(key, html);
    }
    return html;
}

// full diff markup for the unified (mobile) view box. THE html-string
// view: the box is painted via x-fade-html, and token fade requires
// whole-content repaints (x-for rows can't survive that), so this view
// generates its row markup here instead of in the template. all text goes
// through escapeHtml or hljs (whose output is escaped), so it's safe markup.
function diffHtml(original, replacement, lang, cacheKey) {
    // memoized + throttled while the args stream in (see streamMemo)
    return streamMemo('edit:' + cacheKey, [original, replacement, lang],
        () => _diffHtmlNow(original, replacement, lang));
}

function _diffHtmlNow(original, replacement, lang) {
    const clsFor = sign =>
        sign === '..' ? 'diff-gap' : sign === '-' ? 'diff-del' : sign === '+' ? 'diff-add' : 'diff-ctx';
    let rows;
    if (!original && !replacement) return '';
    if (!original || !replacement) {
        // while only one side has streamed in, show it as context/plain
        const solo = (original || replacement || '').replace(/\n$/, '').split('\n');
        rows = solo.map(t => [' ', t]);
    } else {
        rows = collapseContext(diffLines(original, replacement), 2);
    }
    return rows.map(([sign, text]) => {
        const gutter = sign === '..' ? '..' : sign;
        const body = sign === '..' ? escapeHtml(text) : highlightDiffLine(text, lang);
        return `<div class="diff-line ${clsFor(sign)}">` +
            `<span class="diff-gutter">${gutter}</span>` +
            `<span class="diff-text">${body}</span></div>`;
    }).join('');
}

// pairs the linear diff rows into split-view rows: consecutive -/+ runs are
// matched up line-by-line (shorter side gets an empty filler cell), while
// context and gap rows span the full width, like github's split view.
function sideBySideRows(rows) {
    const out = [];
    let dels = [], adds = [];
    const flush = () => {
        const n = Math.max(dels.length, adds.length);
        for (let k = 0; k < n; k++)
            out.push({
                left: k < dels.length ? dels[k] : null,
                right: k < adds.length ? adds[k] : null,
            });
        dels = []; adds = [];
    };
    for (const [sign, text] of rows) {
        if (sign === '-') dels.push(text);
        else if (sign === '+') adds.push(text);
        else { flush(); out.push({ full: text, kind: sign === '..' ? 'gap' : 'ctx' }); }
    }
    flush();
    return out;
}

// full side-by-side markup for the desktop diff view. css shows either
// this or the unified diffHtml, never both (see custom_tool_views.css);
// no line numbers - the cell tints convey which side is which. memoized
// like diffHtml: each box keeps its own memo entry, so the hidden one
// only recomputes on real arg changes.
// side-by-side counterpart of diffHtml. which one VISIBLE is pure css:
// .diff-container is a size container and a container query swaps the
// layouts at a min card width (custom_tool_views.css) - so the switch
// follows the chat/message width settings and resizes with zero JS.
// both layouts render regardless; the per-line highlight cache is shared
// between them, so the second render is mostly just the LCS + string work
// (edit snippets are small, and streamMemo throttles either way).
function diffSideHtml(original, replacement, lang, cacheKey) {
    return streamMemo('edit2:' + cacheKey, [original, replacement, lang],
        () => _diffSideHtmlNow(original, replacement, lang));
}

function _diffSideHtmlNow(original, replacement, lang) {
    if (!original && !replacement) return '';
    let rows;
    // cells carry the same +/- gutter as the unified view: flex row of
    // gutter span + code, so the sign stays put when the code wraps
    const cell = (gutter, text, cls) =>
        `<div class="diff2-cell ${cls}"><span class="diff2-gutter">${gutter}</span>` +
        `<span class="diff2-text">${highlightDiffLine(text, lang) || '\u200b'}</span></div>`;
    if (!original || !replacement) {
        // while only one side has streamed in, keep the two-column layout:
        // the streamed code sits plain (no tint, no gutter sign) in its
        // own column - old left, new right - the other stays empty filler
        const solo = (original || replacement || '').replace(/\n$/, '').split('\n')
            .map(t => '<div class="diff2-row diff2-changed">' +
                (original
                    ? cell('', t, '') + '<div class="diff2-cell diff2-empty"></div>'
                    : '<div class="diff2-cell diff2-empty"></div>' + cell('', t, '')) +
                '</div>').join('');
        return solo;
    }
    rows = collapseContext(diffLines(original, replacement), 2);
    return sideBySideRows(rows).map(p => {
        if (p.full !== undefined) {
            if (p.kind === 'ctx') {
                // unchanged lines sit plain in the left column, like the
                // solo streaming rows - no full-width spanning rows
                return '<div class="diff2-row diff2-ctx">' +
                    cell('', p.full, '') +
                    '<div class="diff2-cell diff2-empty"></div></div>';
            }
            // collapsed-unchanged marker stays a full-width meta row
            return `<div class="diff2-row diff2-gap">` +
                `<div class="diff2-cell diff2-full"><span class="diff2-gutter">..</span>` +
                `<span class="diff2-text">${escapeHtml(p.full)}</span></div></div>`;
        }
        return '<div class="diff2-row diff2-changed">' +
            (p.left === null ? '<div class="diff2-cell diff2-empty"></div>' : cell('-', p.left, 'diff2-del')) +
            (p.right === null ? '<div class="diff2-cell diff2-empty"></div>' : cell('+', p.right, 'diff2-add')) +
            '</div>';
    }).join('');
}

document.addEventListener('alpine:init', () => {
    // coder file edits: show the change as a diff, live while the args stream
    registerToolDisplay({
        match: /^coder_file_edit$/,
        view: 'coder-file-edit'
        // the +N −M header hint is backend-owned now (_metadata.result_summary
        // via coder's _tool_summary) - see renderers/tool_display.js
    });
});
