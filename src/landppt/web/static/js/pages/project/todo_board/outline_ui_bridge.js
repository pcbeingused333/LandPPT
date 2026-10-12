// Ant owns the visible editor; the existing controller owns SSE and recovery.
// Keep its DOM as an inert state adapter until the controller can be extracted.
(() => {
    let regenerating = false;
    function snapshot() {
        const section = document.getElementById('outline-section');
        const json = document.querySelector('#outline-content-display pre')?.textContent || '';
        let outline = null;
        try {
            const value = JSON.parse(json);
            if (Array.isArray(value?.slides) && value.slides.length) outline = value;
        } catch { /* A stream or placeholder is not a completed outline. */ }
        const errorNode = document.getElementById('outline-error-new');
        const error = errorNode && errorNode.style.display !== 'none' ? lastOutlineErrorMessage : '';
        const loading = outlineGenerationStarted || regenerating || (!outline && !error && section?.classList.contains('outline-loading-active'));
        const start = document.getElementById('start-ppt-button');
        return { visible: !!section, loading: !!loading, error: loading ? '' : error, outline: loading ? null : outline,
            canStart: !!outline && !loading && !!start && start.style.display !== 'none',
            language: getOutlineLanguageCode(outline) };
    }
    window.LandPPTTodoUI = {
        snapshot,
        subscribe(listener) {
            let previous = '';
            const update = () => {
                const value = snapshot(), signature = JSON.stringify(value);
                if (signature !== previous) { previous = signature; listener(value); }
            };
            const observer = new MutationObserver(update);
            observer.observe(document.getElementById('todoLegacyHost'), { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ['class', 'style'] });
            const host = document.getElementById('todoLegacyHost');
            host.addEventListener('outline-idle', update);
            update();
            return () => { observer.disconnect(); host.removeEventListener('outline-idle', update); };
        },
        beginOutline() {
            if (unattendedActive || outlineGenerationStarted || regenerating) return;
            showOutlineSection();
            startOutlineGenerationNew();
        },
        async regenerate(requirements) {
            if (unattendedActive || outlineGenerationStarted || regenerating) return;
            regenerating = true;
            try { await regenerateOutlineNew(requirements); }
            finally { regenerating = false; document.getElementById('todoLegacyHost').dispatchEvent(new Event('outline-idle')); }
        },
        saved(outline) {
            updateJsonEditor(JSON.stringify(outline, null, 2));
            renderOutlineViewNewWithData(outline);
        },
        startPpt: startPPTGenerationFromOutline,
    };
})();
