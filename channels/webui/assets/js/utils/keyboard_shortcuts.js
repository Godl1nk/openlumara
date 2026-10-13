async function registerKeyboardShortcuts() {
    document.addEventListener('keydown', async (e) => {
        // Ctrl+K / Cmd+K for global search
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
            e.preventDefault();
            const ui = Alpine.store('ui');
            if (ui.currentModal === 'global_search') {
                ui.closeModal();
            } else {
                ui.openModal('global_search');
            }
        }

        // ctrl+b to show/hide the sidebar
        if (e.ctrlKey && e.key.toLowerCase() === 'b') {
            e.preventDefault();
            await Alpine.store('ui').toggleSidebar();
        }
    });
}
