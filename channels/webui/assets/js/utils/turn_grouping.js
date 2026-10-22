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
    const parts = t.split(/(?<=[.!?…])\s+/);
    const s = parts[parts.length - 1].trim();
    if (s.length <= limit) return s;
    const win = s.slice(0, limit);
    // greedy: matches up through the LAST sentence end inside the window
    const term = win.match(/^[\s\S]*[.!?…](?=\s|$)/);
    if (term && term[0].length >= 12) return term[0].trim();
    const sp = win.lastIndexOf(' ');
    return (sp > 20 ? win.slice(0, sp) : win.slice(0, limit - 1)).replace(/\s+$/, '') + '…';
}

// -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-22)
// is a step's reasoning the live tail of the stream right now? used by the
// combined block's initial collapse state so the "collapse thinking by
// default" setting only affects steps that are actively thinking when they
// mount (a step that mounts on its tool calls is not "thinking"). mirrors
// the thinkingActive getter the template uses for the header label.
function stepIsThinkingLive(stepMsg) {
    const msgs = (Alpine.store('stream').turn?.messages) ?? [];
    const last = msgs[msgs.length - 1];
    return !!last && last.step === stepMsg.step && last.type === 'reasoning';
}

// -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-13)
// the backend's build_steps() makes exactly ONE message final: the last
// content-without-toolcalls one. that's wrong for pushed announcements: a
// push that lands right after the assistant's answer is another content-only
// message, so it hijacks the final slot and the real answer gets demoted into
// the Process chain. re-split finalized history turns: every message in the
// trailing run of consecutive content-only assistant messages becomes its own
// final bubble, and the demoted ones are trimmed back out of the chain's
// trailing step (build_steps folds a thought run's content into one step's
// `content` field, joined with \n\n, in order - so the demoted tail is an
// exact suffix of the last step).
function resplitHistoryTurn(turn) {
    if (!turn || turn.role !== 'assistant') return turn;

    const messages = turn.messages || [];
    const finals = [];
    for (let i = messages.length - 1; i >= 0; i--) {
        const m = messages[i];
        if (m.role === 'assistant' && !m.tool_calls &&
            typeof m.content === 'string' && m.content.trim() !== '') {
            finals.unshift(m);
        } else {
            break;
        }
    }

    // single (or no) trailing content message: the backend already got it right
    if (finals.length <= 1) return turn;

    // pull the demoted messages back out of the chain's trailing step.
    // compare against the RAW join (build_steps joins untrimmed content),
    // then tidy the seam left behind.
    const demoted = finals.slice(0, -1).map(m => m.content).join('\n\n');
    const steps = turn.steps || [];
    const last = steps[steps.length - 1];
    if (last && (last.content || '').endsWith(demoted)) {
        last.content = (last.content.slice(0, last.content.length - demoted.length)).trimEnd();
        if (!last.content && !last.reasoning_content &&
            (!last.tool_calls || last.tool_calls.length === 0)) {
            steps.pop();
        }
    }

    // reasoning that rode on these messages already lives in the chain steps
    // (build_steps merges thought-run reasoning, and gives the backend's
    // final message its own Thoughts step) - strip it from the bubbles so it
    // never renders twice. copies only; turn.messages stays pristine.
    for (let i = 0; i < finals.length; i++) {
        if (finals[i].reasoning_content) {
            const copy = { ...finals[i] };
            delete copy.reasoning_content;
            finals[i] = copy;
        }
    }

    turn.steps = steps;
    turn.final_messages = finals;
    return turn;
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
