import { useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Button, Checkbox, Input, Select, Upload } from 'antd';
import { PictureOutlined, EyeOutlined, CommentOutlined, ClearOutlined } from '@ant-design/icons';

type Source = HTMLButtonElement | HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;
type Record = { node: Source; host: HTMLSpanElement; key: number; focus: () => void; blur: (event: Event) => void; invalid: (event: Event) => void };
const noExtraRoots: HTMLElement[] = [];
let formSequence = 0;

function label(node: Source) {
  const compact = ({ aiImageUploadBtn: '上传图片', aiNativeImageUploadBtn: '上传图片', aiVisionToggleBtn: '视觉模式', aiClearContextBtn: '清除上下文', aiNativeClearContextBtn: '清除上下文' } as {[id:string]:string})[node.id];
  if (compact) return compact;
  if (node.matches('.ai-clear-context-btn')) return '清除上下文';
  if (node.matches('.ai-native-dialog-btn')) return '自由对话';
  if (node.getAttribute('aria-label')) return node.getAttribute('aria-label')!;
  if (node.matches('.speech-script-edit')) return '演讲稿内容';
  if (node instanceof HTMLButtonElement) return node.textContent?.trim() || node.title || '操作';
  const wrap = node.closest('label')?.cloneNode(true) as HTMLElement | undefined;
  wrap?.querySelectorAll('input,select,textarea,[data-native-ant-host]').forEach(child => child.remove());
  const external = node.labels?.[0]?.cloneNode(true) as HTMLElement | undefined;
  external?.querySelectorAll('input,select,textarea,[data-native-ant-host]').forEach(child => child.remove());
  const preceding = node.previousElementSibling?.tagName === 'LABEL' ? node.previousElementSibling.textContent?.trim() : '';
  return wrap?.textContent?.trim() || external?.textContent?.trim() || preceding || node.getAttribute('placeholder') || '输入';
}

// Original nodes own values, validation and listeners. Ant controls forward one
// native event, so the existing requests and draft/stream lifecycle stay intact.
export function NativeControls({ root, extraRoots = noExtraRoots }: { root: HTMLElement; extraRoots?: HTMLElement[] }) {
  const records = useRef(new Map<Source, Record>());
  const invalid = useRef(new Set<Source>());
  const [, refresh] = useState(0);
  useLayoutEffect(() => {
    let next = 0, disposed = false, queued = false;
    const sources = [root, ...extraRoots];
    function sync() {
      queued = false;
      if (disposed) return;
      for (const [node, record] of records.current) {
        if (!sources.some(source => source.contains(node))) { records.current.delete(node); node.removeEventListener('focus', record.focus); node.removeEventListener('blur', record.blur, true); node.removeEventListener('invalid', record.invalid); record.host.remove(); }
        else if (!node.classList.contains('native-ant-source')) node.classList.add('native-ant-source');
      }
      sources.forEach(source => source.querySelectorAll<Source>('button,input:not([type=radio]):not([type=color]):not([type=range]),textarea,select').forEach(node => {
        if (records.current.has(node) || node.closest('[data-native-ant-host],.CodeMirror,.ant-segmented') || node.matches('.ant-btn,.ant-modal-close,.pw-page-pick,[data-bs-dismiss],.btn-close,#freeTemplateCodeArea') || node.querySelector('iframe,img')) return;
        if (node instanceof HTMLInputElement && !['text', 'search', 'number', 'url', 'email', 'password', 'checkbox', 'file'].includes(node.type)) return;
        const host = document.createElement('span'); host.dataset.nativeAntHost = ''; host.className = `native-ant-control native-ant-${node.tagName.toLowerCase()}`;
        if (node instanceof HTMLInputElement && node.type === 'checkbox') host.classList.add('native-ant-checkbox');
        (host as any).nativeSource = node;
        const focused = document.activeElement === node;
        const blur = (event: Event) => { if (event.isTrusted) event.stopImmediatePropagation(); };
        const showInvalid = (event: Event) => { event.preventDefault(); invalid.current.add(node); refresh(value => value + 1); host.querySelector<HTMLElement>('input,textarea,[tabindex="0"]')?.focus(); };
        node.addEventListener('blur', blur, true); node.addEventListener('invalid', showInvalid);
        node.after(host); node.classList.add('native-ant-source');
        const focus = () => host.querySelector<HTMLElement>('input,textarea,button,[tabindex="0"]')?.focus();
        node.addEventListener('focus', focus);
        records.current.set(node, { node, host, key: ++next, focus, blur, invalid: showInvalid });
        if (focused) requestAnimationFrame(focus);
      }));
      refresh(value => value + 1);
    }
    const observer = new MutationObserver(changes => {
      if (changes.every(change => (change.target instanceof Element ? change.target : change.target.parentElement)?.closest('[data-native-ant-host]'))) return;
      if (!queued) { queued = true; queueMicrotask(sync); }
    });
    const scope = root.closest('.ant-modal') || root;
    observer.observe(scope, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ['disabled', 'hidden', 'style', 'class', 'aria-current', 'checked', 'value'] });
    scope.addEventListener('input', sync); scope.addEventListener('change', sync);
    sync();
    return () => {
      disposed = true; observer.disconnect(); scope.removeEventListener('input', sync); scope.removeEventListener('change', sync);
      const previous = Array.from(records.current.values()); records.current.clear();
      previous.forEach(({ node, host, focus, blur, invalid }) => { node.removeEventListener('focus', focus); node.removeEventListener('blur', blur, true); node.removeEventListener('invalid', invalid); node.classList.remove('native-ant-source'); host.remove(); });
    };
  }, [root, extraRoots]);
  function changed(node: Source, value: string | boolean) {
    if (typeof value === 'boolean' && node instanceof HTMLInputElement) node.checked = value;
    else node.value = String(value);
    invalid.current.delete(node);
    node.dispatchEvent(new Event('input', { bubbles: true })); node.dispatchEvent(new Event('change', { bubbles: true }));
    refresh(value => value + 1);
  }
  return <>{Array.from(records.current.values()).map(({ node, host, key }) => {
    const name = label(node); const disabled = node.disabled;
    host.hidden = node.hidden || node.style.display === 'none' || node.classList.contains('hidden') || node.classList.contains('d-none');
    const aria = { 'aria-label': name };
    const field = node as HTMLInputElement;
    const status = invalid.current.has(node) ? 'error' as const : undefined;
    const blur = () => { if (node.isConnected && records.current.has(node)) node.dispatchEvent(new FocusEvent('blur')); };
    const keyDown = (event: React.KeyboardEvent) => {
      // Forward Enter shortcuts but keep Tab/Escape under Ant's focus handling.
      if (event.key === 'Enter') { const forwarded = new KeyboardEvent(event.type, { key: event.key, ctrlKey: event.ctrlKey, metaKey: event.metaKey, bubbles: true, cancelable: true }); if (!node.dispatchEvent(forwarded)) event.preventDefault(); else if (event.type === 'keydown' && node instanceof HTMLInputElement && node.form && !event.ctrlKey && !event.metaKey) { event.preventDefault(); node.form.requestSubmit(); } }
    };
    const primary = /primary|accent/.test(node.className) || node.classList.contains('active') || node.matches('#aiSendBtn,#aiNativeSendBtn,.speech-btn-dark,.outline-modal-btn--solid,.tpl-confirm-btn,.image-library-action:not(.secondary),.ai-optimize-confirm');
    const icon = node.matches('#aiImageUploadBtn,#aiNativeImageUploadBtn') ? <PictureOutlined aria-hidden /> : node.id === 'aiVisionToggleBtn' ? <EyeOutlined aria-hidden /> : node.matches('#aiClearContextBtn,#aiNativeClearContextBtn,.ai-clear-context-btn') ? <ClearOutlined aria-hidden /> : node.matches('.ai-native-dialog-btn') ? <CommentOutlined aria-hidden /> : undefined;
    const control = node instanceof HTMLButtonElement ? <Button {...aria} title={node.title || name} icon={icon} disabled={disabled} danger={node.matches('.danger,.btn-danger,.btn-outline-danger,.lp-share-btn-danger')} type={primary ? 'primary' : node.classList.contains('pw-quiet') ? 'text' : 'default'} htmlType="button" onClick={() => node.click()}>{icon ? null : name}</Button>
      : node instanceof HTMLSelectElement ? <Select {...aria} status={status} value={node.value} disabled={disabled} virtual={false} options={Array.from(node.options).map(option => ({ value: option.value, label: option.textContent, disabled: option.disabled }))} onChange={value => changed(node, value)} getPopupContainer={() => host.closest<HTMLElement>('.ant-modal-container') || document.body} />
      : field.type === 'file' ? <span className="native-ant-file"><Upload name="" disabled={disabled} accept={field.accept} multiple={field.multiple} showUploadList={false} beforeUpload={(file, files) => {
        if (files[0] === file) { const transfer = new DataTransfer(); files.forEach(item => transfer.items.add(item)); field.files = transfer.files; field.dispatchEvent(new Event('change', { bubbles: true })); }
        return false;
      }}><Button disabled={disabled}>选择文件</Button></Upload><span title={Array.from(field.files || []).map(file => file.name).join('、')}>{Array.from(field.files || []).map(file => file.name).join('、') || '尚未选择文件'}</span></span>
      : field.type === 'checkbox' ? <Checkbox {...aria} disabled={disabled} checked={field.checked} onClick={event => event.stopPropagation()} onChange={event => changed(node, event.target.checked)} />
      : node instanceof HTMLTextAreaElement ? <Input.TextArea {...aria} status={status} value={node.value} disabled={disabled} rows={node.rows} maxLength={node.maxLength > 0 ? node.maxLength : undefined} placeholder={node.placeholder} onChange={event => changed(node, event.target.value)} onBlur={blur} onKeyDown={keyDown} onKeyPress={keyDown} />
      : <Input {...aria} status={status} type={field.type} value={node.value} disabled={disabled} min={field.min} max={field.max} step={field.step} maxLength={field.maxLength > 0 ? field.maxLength : undefined} placeholder={field.placeholder} onChange={event => changed(node, event.target.value)} onBlur={blur} onKeyDown={keyDown} onKeyPress={keyDown} />;
    return createPortal(<>{control}{status && <span role="alert" className="native-ant-validation">{node.validationMessage}</span>}</>, host, String(key));
  })}</>;
}

export function nativeEscape(target: EventTarget) {
  const host = target instanceof Element ? target.closest<HTMLElement>('[data-native-ant-host]') : null;
  const source = (host as any)?.nativeSource as Source | undefined;
  if (!source) return false;
  const event = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
  Object.defineProperty(event, 'landpptForwarded', { value: true });
  return !source.dispatchEvent(event);
}

export function nativeSelectIsOpen(target: EventTarget) {
  return target instanceof Element && (target.getAttribute('aria-expanded') === 'true' && target.getAttribute('role') === 'combobox' || !!target.closest('.ant-select-dropdown:not(.ant-select-dropdown-hidden)'));
}

export function NativeNodes({ nodes }: { nodes: Node[] }) {
  const target = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const origins = nodes.map(node => ({ node, parent: node.parentNode, next: node.nextSibling }));
    keepNativeSubmitForms(nodes);
    nodes.forEach(node => target.current?.appendChild(node));
    return () => origins.forEach(({ node, parent, next }) => { if (parent && node.isConnected) parent.insertBefore(node, next?.parentNode === parent ? next : null); });
  }, [nodes]);
  return <div ref={target} className="native-ant-content" />;
}

// A moved footer's submit buttons must still submit their original form.
export function keepNativeSubmitForms(nodes: Node[]) {
    nodes.forEach(node => {
      if (node instanceof Element) node.querySelectorAll<HTMLButtonElement>('button').forEach(button => {
        if (button.type !== 'submit' || !button.form) return;
        if (!button.form.id) button.form.id = `native-ant-form-${++formSequence}`;
        button.setAttribute('form', button.form.id);
      });
    });
}
