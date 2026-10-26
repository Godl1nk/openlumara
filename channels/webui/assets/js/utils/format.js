/*
 * --- formatting stuff
 */
const _escapeReplacements = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
};

function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, (c) => _escapeReplacements[c]);
}

function localDayKey(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
}

function formatLabel(key) {
    if (typeof key !== 'string') return key;
    return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatMessageTimestamp(turn) {
    const messages = turn && turn.messages ? turn.messages : [];
    const ts = (messages[0]?._metadata ?? {}).timestamp;
    if (!ts) return '';

    const date = new Date(ts * 1000);
    if (isNaN(date.getTime())) return '';

    // hour12: false forces 24-hour time regardless of locale
    const time = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });

    const today = new Date();
    if (localDayKey(date) === localDayKey(today)) return time;

    const startOfDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    const diffDays = Math.round((startOfToday - startOfDay) / 86400000);

    if (diffDays === 1) return `Yesterday ${time}`;
    if (diffDays > 1 && diffDays < 7) {
        return `${date.toLocaleDateString('en-US', { weekday: 'long' })} ${time}`;
    }
    if (date.getFullYear() === today.getFullYear()) {
        return `${date.toLocaleDateString('en-US', { month: 'long', day: 'numeric' })} ${time}`;
    }
    return `${date.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })} ${time}`;
}