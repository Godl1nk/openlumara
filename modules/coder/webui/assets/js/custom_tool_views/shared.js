/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-25) harness:openlumara
   helpers shared by more than one coder view: language detection from the
   file path, and the sandbox/path footer line. the streaming memo +
   highlighting machinery they build on lives in the webui's
   renderers/custom_tool_views/shared.js. */

// pick an hljs language from the file extension; undefined -> auto-detect.
const READ_LANG_BY_EXT = {
    py: 'python', js: 'javascript', mjs: 'javascript', ts: 'typescript',
    json: 'json', html: 'html', xml: 'xml', css: 'css', scss: 'scss',
    yml: 'yaml', yaml: 'yaml', md: 'markdown', rs: 'rust', go: 'go',
    c: 'c', h: 'c', cpp: 'cpp', hpp: 'cpp', sh: 'bash', bash: 'bash',
    toml: 'ini', ini: 'ini', sql: 'sql', java: 'java', rb: 'ruby',
    php: 'php', txt: 'plaintext',
};

function langForPath(path) {
    const ext = (path || '').split('.').pop()?.toLowerCase();
    return READ_LANG_BY_EXT[ext];
}

// footer text for the coder views: sandbox name in front of the path,
// eg. "dev: foo/bar.py". falls back to the bare path if no sandbox parsed.
function coderFooterText(args) {
    if (!args.path) return '';
    return args.sandbox ? args.sandbox + ': ' + args.path : args.path;
}
