/*
 * -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
 * step grouping now lives in the backend (core/turns.py): history turns
 * arrive with a ready-made `steps` list, streaming segments carry a `step`
 * number + `step_status` stamped by group_stream. what's left here:
 *  - streamSteps(): fold the active-step-only stream segments into step
 *    objects shaped exactly like the backend history steps
 *  - streamTurnSplit(): the final-content-detection heuristic the backend
 *    can't know mid-stream
 * failed flags, collapsed-header labels and the one-line tool arg hint
 * (now tool.summary, stamped in core/turns.py) are all backend-side.
 */

// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
// group streaming segments by the step number the backend stamped on them
// into objects shaped like the backend's history steps. segments of one
// step: reasoning runs, narration content, then the tool_calls segment
// that carries the step's status + modules.
function streamSteps(chain) {
    const steps = new Map();
    for (const m of chain) {
        if (m.step == null) continue;
        let s = steps.get(m.step);
        if (!s) {
            s = { step: m.step, status: 'thinking', reasoning_content: '', content: '', tool_calls: [], modules: [] };
            steps.set(m.step, s);
        }
        if (m.reasoning_content && m.reasoning_content.trim() !== '') {
            s.reasoning_content += (s.reasoning_content ? '\n\n' : '') + m.reasoning_content;
        }
        if (!m.tool_calls && typeof m.content === 'string' && m.content.trim() !== '') {
            s.content += (s.content ? '\n\n' : '') + m.content;
        }
        if (Array.isArray(m.tool_calls) && m.tool_calls.length > 0) {
            s.tool_calls = m.tool_calls;
            s.modules = m.modules ?? [];
        }
        // status: the backend stamps step_status on every yielded segment;
        // a step with tools takes the tool segment's status (running ->
        // done/failed as responses land), a tool-less step stays thinking
        s.status = (s.tool_calls.length > 0)
            ? (m.step_status ?? (s.status === 'thinking' ? 'running' : s.status))
            : (m.step_status ?? s.status);
        s._tail = m;
    }
    // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-12)
    // fold a tools-only step into the thoughts-only step right before it.
    // group_stream bumps the step counter whenever a tool_calls segment
    // arrives after the current step already attached tools, so providers
    // that interleave tool responses with late tool batches (or emit
    // tool-only rounds) split a beat's thought from its action live.
    // group_history folds a thought run + the tool segment that follows
    // into one step, so merge the same way here and the chain stops
    // reshaping itself when the turn reloads from history
    const list = Array.from(steps.values());
    const merged = [];
    for (const s of list) {
        const prev = merged[merged.length - 1];
        if (prev && s.tool_calls.length > 0 && !s.reasoning_content && !s.content
            && prev.tool_calls.length === 0 && (prev.reasoning_content || prev.content)) {
            prev.tool_calls = s.tool_calls;
            prev.modules = s.modules;
            prev.status = s.status;
            prev._tail = s._tail ?? prev._tail;
            continue;
        }
        merged.push(s);
    }
    return merged;
}

// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-12)
// header preview of a thought: first line, cut at the last sentence
// terminator that still fits within max chars, otherwise a clean word
// cut with an ellipsis. no mid-word pixel guillotines in the chain.
function thoughtSnippet(text, max) {
    const s = (text || '').trim().split('\n')[0].trim();
    const limit = max || 80;
    if (s.length <= limit) return s;
    const win = s.slice(0, limit);
    // greedy: matches up through the LAST sentence end inside the window
    const term = win.match(/^[\s\S]*[.!?…](?=\s|$)/);
    if (term && term[0].length >= 12) return term[0].trim();
    const sp = win.lastIndexOf(' ');
    return (sp > 20 ? win.slice(0, sp) : win.slice(0, limit - 1)).replace(/\s+$/, '') + '…';
}

// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
// while streaming we can't know which content will be the final one:
// content only counts as final while it is the most recent segment. if a
// reasoning/toolcall segment arrives afterwards, it gets pulled back into
// the chain automatically
function streamTurnSplit(turn) {
    const messages = turn?.messages || [];
    const last = messages[messages.length - 1];

    // empty segments are already filtered out backend-side (group_stream
    // only yields segments with visible content), so no filter here
    if (last && last.type === 'content' && !last.tool_calls) {
        return { chain: messages.slice(0, -1), final: [last] };
    }

    return { chain: messages, final: [] };
}
