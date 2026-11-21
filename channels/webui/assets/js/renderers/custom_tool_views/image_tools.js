// -- AI GENERATED CODE (GPT-6) :: 2026-11-21 17:42:04 +08:00 harness:Codex
// image generation/editing tool cards. markup lives in chat/tool_displays.html,
// styling in chat/custom_tool_views.css.
const IMAGE_TOOL_VIEW_PATH = '/api/ext/image_tools/view';

function isImageToolView(url) {
    if (!url) return false;
    try {
        const parsed = new URL(url, window.location.href);
        return parsed.origin === window.location.origin && parsed.pathname === IMAGE_TOOL_VIEW_PATH;
    } catch {
        return false;
    }
}

// -- AI GENERATED CODE (GPT-6) :: 2026-11-21 18:19:00 +08:00 harness:Codex
function bindImageToolFile(element, attribute, url, download = null) {
    const request = new AbortController();
    let objectUrl;
    let observer;
    element.removeAttribute(attribute);
    download?.removeAttribute('href');

    async function load() {
        try {
            const response = await fetch(url, { signal: request.signal, redirect: 'error' });
            if (!response.ok || !response.headers.get('content-type')?.startsWith('image/')) return;
            const blob = await response.blob();
            if (request.signal.aborted) return;
            objectUrl = URL.createObjectURL(blob);
            element.setAttribute(attribute, objectUrl);
            download?.setAttribute('href', objectUrl);
        } catch {
            // Keep the image unavailable on network failure or navigation.
        }
    }

    if (element.loading === 'lazy' && typeof IntersectionObserver !== 'undefined') {
        observer = new IntersectionObserver(entries => {
            if (!entries.some(entry => entry.isIntersecting)) return;
            observer.disconnect();
            if (!request.signal.aborted) load();
        });
        observer.observe(element);
    } else {
        load();
    }

    return () => {
        observer?.disconnect();
        request.abort();
        if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
}

document.addEventListener('alpine:init', () => {
    Alpine.directive('image-tool-file', (element, { expression, value }, { evaluateLater, effect, cleanup }) => {
        const viewer = value === 'viewer';
        const target = viewer ? element.querySelector('img') : element;
        const download = viewer ? element.querySelector('a.download') : null;
        const attribute = viewer ? 'src' : value || 'src';
        const getUrl = evaluateLater(expression);
        let release;
        effect(() => getUrl(url => {
            release?.();
            if (isImageToolView(url)) {
                release = bindImageToolFile(target, attribute, url, download);
            } else {
                release = undefined;
                target.removeAttribute(attribute);
                download?.removeAttribute('href');
            }
        }));
        cleanup(() => release?.());
    });
    registerToolDisplay({
        match: /^image_tools_(generate|resize|crop|rotate|flip|apply_filter|add_text|convert_format)$/,
        view: 'image-result',
        summary: res => res?.content?.filename || ''
    });
});

const IMAGE_TOOL_ACTION = /^(tools_)?(generate|resize|crop|rotate|flip|apply_filter|add_text|convert_format)$/;

// steps start expanded when they contain an image so the picture is visible
function stepHasImageResult(step) {
    for (const group of (step?.modules ?? [])) {
        if (!['image', 'image_tools'].includes(String(group?.module || '').toLowerCase())) continue;
        for (const action of (group?.actions ?? [])) {
            if (IMAGE_TOOL_ACTION.test(action?.name || '')) return true;
        }
    }
    return false;
}

function turnHasImageResult(turn) {
    if ((turn?.steps ?? []).some(stepHasImageResult)) return true;
    for (const segment of (turn?.messages ?? [])) {
        for (const tool of (segment?.tool_calls ?? [])) {
            if (toolDisplayView(tool) === 'image-result') return true;
        }
    }
    return false;
}
