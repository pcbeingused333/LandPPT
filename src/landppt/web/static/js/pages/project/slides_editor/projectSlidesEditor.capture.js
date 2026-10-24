// Shared screenshot support. Keep the renderer local and scoped to its document;
// a hidden editor iframe has a 0x0 viewport in continuous/code view.
const html2CanvasLoads = new WeakMap();

function loadHtml2Canvas(targetWindow = window) {
    if (typeof targetWindow.html2canvas === 'function') return Promise.resolve(targetWindow.html2canvas);
    const doc = targetWindow.document;
    if (html2CanvasLoads.has(doc)) return html2CanvasLoads.get(doc);
    const pending = new Promise((resolve, reject) => {
        const script = doc.createElement('script');
        let settled = false;
        const finish = (error) => {
            if (settled) return;
            settled = true;
            clearTimeout(timer);
            script.remove();
            if (error) reject(error);
            else resolve(targetWindow.html2canvas);
        };
        const timer = setTimeout(() => finish(new Error('截图组件加载超时，请重试')), 8000);
        script.src = new URL('/static/js/vendor/html2canvas-1.4.1.min.js', window.location.origin).href;
        script.onload = () => finish(typeof targetWindow.html2canvas === 'function' ? null : new Error('截图组件加载失败，请重试'));
        script.onerror = () => finish(new Error('截图组件加载失败，请重试'));
        (doc.head || doc.documentElement).appendChild(script);
    }).catch(error => { html2CanvasLoads.delete(doc); throw error; });
    html2CanvasLoads.set(doc, pending);
    return pending;
}

function waitForCaptureLoad(frame) {
    return new Promise(resolve => {
        const done = () => { clearTimeout(timer); frame.removeEventListener('load', done); resolve(); };
        const timer = setTimeout(done, 2500);
        frame.addEventListener('load', done, { once: true });
    });
}

async function withSlideCaptureFrame(index, capture) {
    const mainFrame = document.getElementById('slideFrame');
    const continuousFrame = document.querySelector(`.continuous-slide[data-slide-index="${index}"] iframe`);
    const rendered = frame => frame && frame.contentWindow?.innerWidth > 0 && frame.contentWindow?.innerHeight > 0;
    let frame = rendered(continuousFrame) ? continuousFrame : mainFrame;
    let temporary = false;
    try {
        if (!rendered(frame)) {
            // The hidden main iframe may still contain the previously selected
            // page until its scheduled preview update runs.
            const source = slidesData[index]?.html_content;
            const html = source ? prepareHtmlForPreview(source) : mainFrame?.getAttribute('srcdoc');
            if (!html) throw new Error('当前页尚未就绪，请稍后重试');
            frame = document.createElement('iframe');
            temporary = true;
            frame.dataset.slideCapture = 'true';
            frame.setAttribute('aria-hidden', 'true');
            frame.tabIndex = -1;
            // Offscreen rather than display:none: the browser must perform layout.
            frame.style.cssText = 'position:fixed;left:-10000px;top:0;width:1280px;height:720px;border:0;pointer-events:none;color-scheme:light';
            const loaded = waitForCaptureLoad(frame);
            frame.srcdoc = html;
            document.body.appendChild(frame);
            await loaded;
        } else if (frame.contentDocument?.readyState !== 'complete') {
            await waitForCaptureLoad(frame);
        }
        const doc = frame.contentDocument;
        if (!doc?.body || !rendered(frame)) throw new Error('当前页尚未就绪，请稍后重试');
        const ready = [doc.fonts?.ready, ...Array.from(doc.images).filter(image => !image.complete).map(image => image.decode().catch(() => {}))];
        let timer;
        try {
            await Promise.race([Promise.allSettled(ready), new Promise(resolve => { timer = setTimeout(resolve, 1500); })]);
        } finally { clearTimeout(timer); }
        const renderer = await loadHtml2Canvas(frame.contentWindow);
        if (currentSlideIndex !== index || doc !== frame.contentDocument) throw new Error('页面已切换，请重新尝试截图');
        const result = await capture(renderer, doc);
        if (currentSlideIndex !== index || doc !== frame.contentDocument) throw new Error('页面已切换，请重新尝试截图');
        return result;
    } finally {
        if (temporary) frame?.remove();
    }
}
