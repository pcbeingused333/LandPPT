(() => {
    'use strict';
    // UI-only replacement for Bootstrap's wizard frame. Keep the event names
    // consumed by the existing generation controller and promise cleanup.
    window.LandPPTGeneratorUI = {
        createModal(element) {
            return {
                show() {
                    element.dataset.antOpen = 'true';
                    element.setAttribute('aria-hidden', 'false');
                    setTimeout(() => element.dispatchEvent(new Event('shown.bs.modal')), 50);
                },
                hide() {
                    if (element.dataset.antOpen !== 'true') return;
                    element.dataset.antOpen = 'false';
                    element.setAttribute('aria-hidden', 'true');
                    // Bootstrap emits hidden after hide() returns. Confirmation
                    // resolves true first; a user cancellation still resolves false.
                    queueMicrotask(() => element.dispatchEvent(new Event('hidden.bs.modal')));
                },
            };
        },
    };
})();
