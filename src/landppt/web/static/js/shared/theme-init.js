(() => {
    'use strict';
    // Apply the saved appearance before first paint. "light" is the 可可蛋白
    // palette in design-tokens.css; no attribute keeps the default dark palette.
    try {
        if (localStorage.getItem('landppt-theme') === 'light') document.documentElement.dataset.theme = 'light';
    } catch (error) { /* Storage may be unavailable; keep the default. */ }
})();
