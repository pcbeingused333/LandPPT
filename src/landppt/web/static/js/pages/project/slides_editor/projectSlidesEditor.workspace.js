/* Layout has explicit state; application controls do not inspect hidden buttons. */
(() => {
    const container = document.querySelector('.editor-container');
    const sidebar = document.getElementById('slidesSidebar');
    const backdrop = document.querySelector('.workspace-sidebar-backdrop');
    const mobile = window.matchMedia('(max-width: 700px)');
    const listeners = new Set();
    let open = !mobile.matches;
    function setSidebar(value) {
        open = value; container.classList.toggle('sidebar-collapsed', !open);
        backdrop.hidden = !open || !mobile.matches;
        if (typeof debounceResize === 'function') debounceResize();
        listeners.forEach(listener => listener(open));
    }
    const hide = () => setSidebar(false);
    const resize = () => setSidebar(!mobile.matches);
    const select = event => { if (mobile.matches && event.target.closest('.slide-thumbnail') && !event.ctrlKey && !event.metaKey) hide(); };
    const escape = event => {
        if (event.key === 'Escape' && mobile.matches && open) {
            hide(); document.querySelector('.editor-ant-header [aria-controls="slidesSidebar"]')?.focus();
        }
    };
    setSidebar(open);
    window.LandPPTEditorLayout = {
        read: () => open, toggle: () => setSidebar(!open),
        subscribe(listener) {
            if (!listeners.size) {
                backdrop.addEventListener('click', hide); mobile.addEventListener('change', resize);
                sidebar.addEventListener('click', select, true); document.addEventListener('keydown', escape);
            }
            listeners.add(listener);
            return () => {
                listeners.delete(listener);
                if (!listeners.size) {
                    backdrop.removeEventListener('click', hide); mobile.removeEventListener('change', resize);
                    sidebar.removeEventListener('click', select, true); document.removeEventListener('keydown', escape);
                }
            };
        },
    };
})();
