/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-25) harness:openlumara
   shell module view: shell_run renders as a terminal - command streams in
   with a blinking cursor, output lands below once the call completes.
   highlightedCode + streamMemo live in the webui's
   renderers/custom_tool_views/shared.js; markup in this module's
   templates/chat/tool_displays.html (tool_views slot); styling in this
   folder's shell.css. */

// flatten a shell tool call into terminal display bits: the command text
// (from args, streams live) plus the combined output (stdout, then stderr,
// then any module errors like timeouts). done = response arrived, which
// hides the blinking cursor. response shape: { status, content:
// { stdout, stderr, exit_code, errors? } }, or content as a plain string
// when the module itself errored before running anything.
function shellViewInfo(tool, cacheKey) {
    const args = toolArgs(tool, cacheKey);
    const resp = toolResponse(tool);
    // a literal newline in the command means it spans lines: the output
    // then gets a dashed divider so where the command ends is clear
    const multiline = String(args.command ?? '').includes('\n');
    if (!resp) {
        // response present but unparseable (plain-string error): show raw
        return {
            command: args.command ?? '',
            // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-13)
            // response lives under the tool call's _metadata key
            output: typeof tool?._metadata?.response === 'string' ? tool._metadata.response : '',
            done: !!tool?._metadata?.response,
            multiline,
        };
    }
    const c = resp.content;
    // module-level error (content is the error string): leave the terminal
    // box empty - the shared .display-error row below the view shows it
    if (resp.status === 'error' && typeof c === 'string')
        return { command: args.command ?? '', output: '', done: true, multiline };
    const parts = [];
    if (typeof c === 'string') parts.push(c);
    else if (c && typeof c === 'object') {
        if (c.stdout) parts.push(c.stdout);
        if (c.stderr) parts.push(c.stderr);
        // errors (timeouts, kills) are NOT mixed into the terminal output:
        // the shared .display-error row below the view shows them in the
        // error color (see toolDisplayError). truncation is a separate,
        // non-fatal note (see truncation_note below)
    }
    let output = parts.join('\n\n');
    // silent non-zero exits would leave an empty box - say something
    if (!output && typeof c === 'object' && c && c.exit_code)
        output = `(exit code ${c.exit_code})`;
    return {
        command: args.command ?? '', output, done: true, multiline,
        note: (typeof c === 'object' && c && c.truncation_note) || '',
    };
}

// bash-highlighted command html, memoized + throttled per view instance
// (see streamMemo): long commands re-highlighting on every getter read per
// streamed chunk would go quadratic.
function shellCommandHtml(command, cacheKey) {
    if (!command) return '';
    return streamMemo('shell:' + cacheKey, [command],
        () => highlightedCode(command, 'bash'));
}

document.addEventListener('alpine:init', () => {
    // sandboxed shell: terminal-style view, command streams in with a
    // blinking cursor, output lands below it once the call completes
    registerToolDisplay({
        match: /^shell_run$/,
        view: 'shell'
        // the "exit N" header hint is backend-owned now
        // (_metadata.result_summary via shell's _tool_summary)
    });
});
