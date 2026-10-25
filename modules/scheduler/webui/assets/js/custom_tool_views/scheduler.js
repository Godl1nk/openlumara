/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-25) harness:openlumara
   scheduler module view: scheduler_add_job renders as a card with clock,
   when + action.
   markup in this module's templates/chat/tool_displays.html (tool_views
   slot); styling in this folder's scheduler.css. */

const WEEKDAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

// derive the display bits from a scheduler job's args. only fields the
// model actually passed show up; everything optional stays hidden.
function schedulerInfo(args) {
    const when = args.relative_duration ?? args.target_time ?? '';
    const tags = [];
    if (args.recurring) tags.push('recurring');
    if (args.weekdays_only) tags.push('weekdays');
    if (Number.isInteger(args.target_weekday))
        tags.push(WEEKDAY_NAMES[args.target_weekday] ?? `day ${args.target_weekday}`);
    return { when, tags, action: args.action ?? '' };
}

document.addEventListener('alpine:init', () => {
    // scheduler jobs: card with clock, when + action
    registerToolDisplay({
        match: /^scheduler_add_job$/,
        view: 'scheduler-job'
        // the "when" header hint is backend-owned now
        // (_metadata.result_summary via scheduler's _tool_summary)
    });
});
