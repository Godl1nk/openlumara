/* -- AI GENERATED CODE (Qwen3.8-Flash-Next-Gufo) :: 2026-11-27 harness:openlumara */
function initMultilineInput() {
    const wrapper = document.querySelector('.input-wrapper');
    const textarea = wrapper?.querySelector('#user-input');
    if (!wrapper || !textarea) return;

    const CLONE_PROPS = [
        'fontStyle', 'fontVariant', 'fontWeight', 'fontStretch', 'fontSize',
        'fontFamily', 'lineHeight', 'letterSpacing', 'wordSpacing',
        'textRendering', 'paddingTop', 'paddingRight', 'paddingBottom',
        'paddingLeft', 'boxSizing', 'wordBreak', 'overflowWrap', 'whiteSpace',
    ];

    let clone = null;

    // width the textarea has with all action buttons visible (the single-line
    // layout), so the wrap point never moves with the class. Read by briefly
    // removing the class: both class flips happen inside one synchronous
    // block, so no frame ever renders the intermediate state.
    const referenceWidth = () => {
        const wasMultiline = wrapper.classList.contains('is-multiline');
        if (wasMultiline) wrapper.classList.remove('is-multiline');
        const width = textarea.clientWidth;
        if (wasMultiline) wrapper.classList.add('is-multiline');
        return width;
    };

    // -- AI GENERATED CODE (GPT-6.2-Sol) :: 2026-11-28 17:59 +08:00 harness:Codex
    const hasMultipleLines = () => {
        const draft = textarea.value;
        if (!draft) return false;

        if (!clone) {
            clone = document.createElement('div');
            clone.setAttribute('aria-hidden', 'true');
            clone.style.position = 'absolute';
            clone.style.top = '0';
            clone.style.left = '-9999px';
            clone.style.visibility = 'hidden';
            clone.style.pointerEvents = 'none';
            clone.style.overflow = 'hidden';
            clone.style.height = 'auto';
            document.body.appendChild(clone);
        }
        const styles = getComputedStyle(textarea);
        for (const prop of CLONE_PROPS) clone.style[prop] = styles[prop];
        clone.style.width = referenceWidth() + 'px';
        // The measuring div needs a character to render a final empty line.
        clone.textContent = draft.endsWith('\n') ? draft + '\u200b' : draft;
        const singleLineHeight = parseFloat(styles.lineHeight) + parseFloat(styles.paddingTop) + parseFloat(styles.paddingBottom);
        return clone.offsetHeight > singleLineHeight + 1;
    };

    let updateQueued = false;
    const scheduleUpdate = () => {
        if (updateQueued) return;
        updateQueued = true;
        requestAnimationFrame(() => {
            updateQueued = false;
            wrapper.classList.toggle('is-multiline', hasMultipleLines());
        });
    };

    new ResizeObserver(scheduleUpdate).observe(textarea);
    document.addEventListener('alpine:initialized', () => {
        // Clearing or restoring a draft can leave the textarea size unchanged.
        Alpine.effect(() => {
            void Alpine.store('chat').user_input;
            scheduleUpdate();
        });
    }, { once: true });
}

initMultilineInput();
