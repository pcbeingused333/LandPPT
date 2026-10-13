// UI adapter only. Native editor modules still own slide data and API requests.
(() => {
    const documentKeys = new WeakMap(), stableDocumentKeys = new Map(); let documentSequence = 0;
    function documentPages() {
        const counts = new Map();
        slidesData.forEach(slide => { if (slide.slide_id) counts.set(slide.slide_id, (counts.get(slide.slide_id) || 0) + 1); });
        const pages = slidesData.map(slide => {
            if (!documentKeys.has(slide)) documentKeys.set(slide, counts.get(slide.slide_id) === 1 && stableDocumentKeys.get(slide.slide_id) || `editor-page-${++documentSequence}`);
            return { key: documentKeys.get(slide), slideId: slide.slide_id || null, title: slide.title || '' };
        });
        stableDocumentKeys.clear();
        pages.forEach(page => { if (counts.get(page.slideId) === 1) stableDocumentKeys.set(page.slideId, page.key); });
        return pages;
    }
    const types = [
        ['.modal', '.modal-title, .speech-modal-title', '.btn-close, .speech-modal-close', '.modal-footer, .speech-modal-footer', 920],
        ['.outline-modal', '.outline-modal__title', '.outline-modal__close', '.outline-modal__footer', 760],
        ['.ai-optimize-modal', '.ai-optimize-title', '.ai-optimize-modal__close', '.ai-optimize-modal__footer', 640],
        ['.tpl-dialog-overlay', '.tpl-dialog-title', '.tpl-dialog-close', '.tpl-dialog-footer', 1180],
        ['.lp-share-modal', '.lp-share-modal-title', '.lp-share-modal-close', '#lpShareActions', 560],
        ['.agent-diff-modal', '.agent-diff-header', '.agent-diff-close', '', 1000],
        ['#imageLibraryOverlay', '.image-library-info h4', '.image-library-close', '.image-library-actions', 1000],
        ['#imagePreviewOverlay', '#imagePreviewTitle', '.image-preview-close', '.image-preview-actions', 900],
        ['#exportOverlay', '#exportTitle', '#exportCancelBtn', '.export-actions', 520],
        ['#aiNativeChatDialog', '.ai-native-chat-dialog-title', '.ai-native-chat-dialog-close', '.ai-native-chat-dialog-footer', 840],
        ['#svg-page-editor', '.svg-editor__title', '[data-close]', '', 1680],
        ['.package-dialog', 'header h2', 'header button', 'footer', 1000],
    ];
    const records = new Map(); let sequence = 0;
    const selector = types.map(type => type[0]).join(',');
    const shown = node => node && !node.hidden && getComputedStyle(node).display !== 'none';
    function readExportProgress(node) {
        const button = node.querySelector('#exportCancelBtn'), icon = node.querySelector('#exportIcon');
        const cancelLabel = button?.textContent.trim() || '';
        return {
            subtitle: node.querySelector('#exportSubtitle')?.textContent || '',
            status: node.querySelector('#exportStatus')?.textContent || '',
            percent: node.querySelector('#exportProgressBar')?.style.width || '',
            kind: icon?.classList.contains('error') ? 'error' : icon?.classList.contains('success') ? 'success' : button?.disabled && /取消/.test(cancelLabel) ? 'cancelling' : 'working',
            cancelVisible: !!shown(button), cancelDisabled: !!button?.disabled, cancelLabel,
        };
    }
    function readShareLinks(node) {
        const narration = node.querySelector('#lpNarrationBlock');
        return {
            presentation: node.querySelector('#lpShareUrlBox')?.textContent || '',
            narration: narration && narration.style.display !== 'none' ? node.querySelector('#lpNarrationUrlBox')?.textContent || '' : '',
        };
    }
    const contextActions = ['editSlide', 'regenerateContextSlide', 'copySlide', 'pasteSlide', 'duplicateSlide', 'insertNewSlide', 'exportSingleSlideHTML', 'exportSingleSlidePptxClient', 'deleteSlide'];
    const contextActionNode = action => contextActions.includes(action) ? document.querySelector(`#contextMenu [onclick="${action}()"]`) : null;
    const contextActionDisabled = node => !node || node.disabled || node.classList.contains('disabled') || node.style.pointerEvents === 'none';
    function readContextMenu() {
        const menu = document.getElementById('contextMenu');
        if (menu.style.display !== 'block' || !slidesData[contextMenuSlideIndex]) return null;
        return {
            x: Number(menu.dataset.antContextX) || 0, y: Number(menu.dataset.antContextY) || 0,
            index: contextMenuSlideIndex, title: slidesData[contextMenuSlideIndex].title || '',
            actions: Object.fromEntries(contextActions.map(action => {
                const node = contextActionNode(action);
                return [action, { disabled: !!contextActionDisabled(node), hidden: !shown(node), hint: node?.style.pointerEvents === 'none' ? node.title : action === 'pasteSlide' ? '请先复制一张幻灯片' : node?.title || '' }];
            })),
        };
    }
    function read() {
        const dialogs = [];
        document.querySelectorAll(selector).forEach(node => {
            if (!shown(node) || node.tagName === 'DIALOG' && !node.open) return;
            let record = records.get(node);
            if (!record) {
                const type = types.find(type => node.matches(type[0]));
                const origin = document.activeElement;
                record = { key: ++sequence, node, type, origin, title: node.querySelector(type[1])?.textContent.trim() || node.getAttribute('aria-label') || '编辑设置' };
                records.set(node, record);
            }
            record.title = node.querySelector(record.type[1])?.textContent.trim() || node.getAttribute('aria-label') || record.title;
            if (record.type[3]) record.footer = node.querySelector(record.type[3]) || (record.footer?.isConnected ? record.footer : null);
            const close = node.querySelector(record.type[2]) || Array.from(node.querySelectorAll('button')).find(button => /^(取消|关闭)$/.test(button.textContent.trim()));
            record.closable = !!close && !close.disabled && close.style.display !== 'none';
            if (node.id === 'exportOverlay') record.exportProgress = readExportProgress(node);
            if (node.matches('.lp-share-modal')) record.shareLinks = readShareLinks(node);
            dialogs.push(record);
        });
        records.forEach((record, node) => { if (!node.isConnected || node.id === 'exportOverlay' && !shown(node)) records.delete(node); });
        const toasts = Array.from(document.querySelectorAll('.progress-toast, #ai-optimize-loading')).map(node => {
            if (!node.dataset.antToastKey) node.dataset.antToastKey = `editor-progress-${++sequence}`;
            const message = node.querySelector('.progress-message')?.textContent || node.textContent;
            if (!node.dataset.antProgressTitle) node.dataset.antProgressTitle = message;
            return { key: node.dataset.antToastKey, title: node.dataset.antProgressTitle, message, percent: node.querySelector('.progress-fill')?.style.width };
        });
        return {
            mode: currentMode, current: currentSlideIndex, count: slidesData.length,
            title: slidesData[currentSlideIndex]?.title || '', selected: selectedSlideIndices.size,
            documentPages: documentPages(),
            documentPanel: document.getElementById('slidesSidebar').dataset.editorPanel || 'slides',
            documentDirty: document.getElementById('slidesSidebar').dataset.documentDirty === 'true',
            documentSaving: document.getElementById('slidesSidebar').dataset.documentSaving === 'true',
            svg: currentSlideIsSvg(), sidebar: !document.querySelector('.editor-container').classList.contains('sidebar-collapsed'),
            aiOpen: document.getElementById('aiEditSidebar').classList.contains('open'),
            aiWidth: Number.parseFloat(document.getElementById('aiEditSidebar').style.width) || 480,
            packageContent: !document.getElementById('packageContentEditorBtn').hidden,
            nativeExport: document.getElementById('exportSvgNativeModeItem').style.display !== 'none',
            vectorExport: document.getElementById('exportSvgVectorModeItem').style.display !== 'none',
            clientExport: document.getElementById('exportClientModeItem').style.display !== 'none',
            dialogs, toasts, contextMenu: readContextMenu(),
        };
    }
    window.LandPPTEditorUI = {
        read,
        applyDocument(key, snapshot) {
            const index = documentPages().findIndex(page => page.key === key);
            if (index < 0 || index !== snapshot.slide_index) return;
            const slide = slidesData[index];
            if (slide.slide_id && snapshot.slide_id !== slide.slide_id) return;
            if (snapshot.slide_id) slide.slide_id = snapshot.slide_id;
            if (!projectOutline) projectOutline = { slides: [] };
            if (!Array.isArray(projectOutline.slides)) projectOutline.slides = [];
            projectOutline.slides[index] = snapshot.outline;
            window.projectOutline = projectOutline;
            if (snapshot.outline.title) slide.title = snapshot.outline.title;
            ['slide_type', 'content_points', 'description'].forEach(field => {
                if (field in snapshot.outline) slide[field] = snapshot.outline[field];
            });
            const title = document.querySelector(`.slide-thumbnail[data-slide-index="${index}"] .slide-title`);
            if (title) {
                const badge = title.querySelector('.slide-mode-badge');
                title.textContent = `${index + 1}. ${slide.title}`;
                if (badge) title.appendChild(badge);
            }
        },
        openSpeechDocument(language, preview) {
            currentSpeechLanguage = language;
            const selector = document.getElementById('speechLanguage');
            if (selector) selector.value = language;
            if (preview) showCurrentSpeechScripts(); else showSpeechScriptDialog();
        },
        subscribe(listener) {
            let previous = '', queued = false, disposed = false;
            const update = () => {
                queued = false; if (disposed) return;
                document.querySelectorAll('.slide-thumbnail').forEach(node => {
                    const label = node.querySelector('.slide-title')?.textContent || '幻灯片';
                    if (node.getAttribute('aria-label') !== label) node.setAttribute('aria-label', label);
                    if (node.dataset.antAccessible) return;
                    node.dataset.antAccessible = 'true'; node.tabIndex = 0; node.setAttribute('role', 'button');
                    node.addEventListener('keydown', event => {
                        if (event.key === 'ContextMenu' || event.key === 'F10' && event.shiftKey) {
                            event.preventDefault(); event.stopPropagation();
                            const rect = node.getBoundingClientRect();
                            showContextMenu({ preventDefault() {}, clientX: rect.left + Math.min(rect.width, 32), clientY: rect.top + Math.min(rect.height, 32) }, Number(node.dataset.slideIndex));
                            return;
                        }
                        if (!['Enter', ' '].includes(event.key)) return;
                        event.preventDefault(); node.dispatchEvent(new MouseEvent('click', { bubbles: true, ctrlKey: event.ctrlKey, metaKey: event.metaKey }));
                    });
                });
                const state = read();
                const signature = JSON.stringify({ ...state, dialogs: state.dialogs.map(item => [item.key, item.title, item.closable, !!item.footer, item.exportProgress, item.shareLinks]) });
                if (signature !== previous) { previous = signature; listener(state); }
            };
            const observer = new MutationObserver(() => { if (!queued) { queued = true; queueMicrotask(update); } });
            observer.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ['class', 'style', 'hidden', 'disabled', 'open', 'data-editor-panel', 'data-document-dirty', 'data-document-saving'] });
            update();
            return () => { disposed = true; observer.disconnect(); };
        },
        openDialog(dialog) { dialog.show(); },
        close(record) {
            const button = record.node.querySelector(record.type[2]);
            if (button && !button.disabled) button.click();
            else {
                const cancel = Array.from(record.node.querySelectorAll('button')).find(node => /^(取消|关闭)$/.test(node.textContent.trim()));
                if (cancel && !cancel.disabled) cancel.click();
                else record.node.click();
            }
        },
        call(name, ...args) { if (typeof window[name] === 'function') return window[name](...args); },
        click(id) { document.getElementById(id)?.click(); },
        runShareAction(record, action) {
            if (!record.node.isConnected || !record.node.matches('.lp-share-modal')) return;
            const label = { copy: '复制链接', open: '打开演示', copyNarration: '复制讲解链接', openNarration: '打开讲解', disable: '禁用分享' }[action];
            const button = Array.from(record.node.querySelectorAll('#lpShareActions button')).find(node => node.textContent.trim() === label);
            if (button && !button.disabled) button.click();
        },
        dismissContextMenu() { hideContextMenu(); },
        cancelExport() {
            const overlay = document.getElementById('exportOverlay'), progress = readExportProgress(overlay);
            if (shown(overlay) && progress.cancelVisible && !progress.cancelDisabled && progress.kind !== 'error') overlay.querySelector('#exportCancelBtn').click();
        },
        dismissExport() {
            const overlay = document.getElementById('exportOverlay');
            if (!shown(overlay) || readExportProgress(overlay).kind !== 'error') return;
            // Dispatch the original failure dismissal so its one-shot listener is removed.
            overlay.click();
            if (overlay.classList.contains('active')) hideExportOverlay();
        },
        runContextAction(action) {
            const menu = readContextMenu(), node = contextActionNode(action);
            if (!menu || contextActionDisabled(node) || !shown(node)) return;
            node.click();
        },
    };
})();
