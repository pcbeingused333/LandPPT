import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Modal, Segmented } from 'antd';
import { NativeControls, NativeNodes, nativeEscape, nativeSelectIsOpen } from './native-controls';
import { modalFocus } from './modal-focus';
import './native-surfaces.css';

type Record = { key: number; node: HTMLDialogElement; origin: HTMLElement | null; footer: HTMLElement | null };

function PackageDialog({ record, index }: { record: Record; index: number }) {
  const workspace = record.node.classList.contains('package-workspace');
  const [pane, setPane] = useState('预览');
  const [content] = useState<Node[]>(() => Array.from(record.node.childNodes).filter(node => node !== record.node.querySelector('header') && node !== record.footer));
  const footer = useMemo<Node[]>(() => record.footer ? [record.footer] : [], [record.footer]);
  const [heading] = useState<Node[]>(() => workspace ? [record.node.querySelector('.pw-title')!] : []);
  const controls = useMemo(() => [...heading.filter((node): node is HTMLElement => node instanceof HTMLElement), ...(record.footer ? [record.footer] : [])], [heading, record.footer]);
  const close = () => {
    const button = record.node.querySelector<HTMLButtonElement>('header > button');
    if (button && !button.disabled) button.click();
  };
  const closable = !record.node.querySelector<HTMLButtonElement>('header > button')?.disabled;
  useLayoutEffect(() => {
    const root = record.node;
    root.classList.add('package-ant-source-dialog'); root.setAttribute('role', 'presentation');
    return () => {
      root.classList.remove('package-ant-source-dialog'); root.removeAttribute('role');
      queueMicrotask(() => { if (!document.querySelector('.package-ant-modal') && record.origin?.isConnected) record.origin.focus(); });
    };
  }, [record.node, record.origin]);
  return <Modal open className={`package-ant-modal${workspace ? ' package-ant-workspace' : ''}`} title={workspace ? <NativeNodes nodes={heading} /> : record.node.querySelector('header h2')?.textContent}
    getContainer={() => record.node}
    width={workspace ? 1320 : record.node.classList.contains('pptx-import') ? 1080 : record.node.classList.contains('package-confirm') ? 560 : 1000} zIndex={2100 + index * 20}
    footer={footer.length ? <NativeNodes nodes={footer} /> : null} closable={closable} keyboard={closable} mask={{ closable: false }} onCancel={close}
    modalRender={node => <div onKeyDownCapture={event => { if (event.key === 'Escape' && !nativeSelectIsOpen(event.target) && !(event.nativeEvent as any).landpptForwarded) { event.stopPropagation(); event.preventDefault(); if (!nativeEscape(event.target) && closable) close(); } }}>{modalFocus(node)}</div>}>
    {workspace && <Segmented block className="package-ant-panes" aria-label="模板包工作区视图" options={['页面', '预览', 'AI 编辑']} value={pane} onChange={setPane} />}
    <div className="package-ant-surface" data-pane={pane}><NativeNodes nodes={content} /></div>
    <NativeControls root={record.node} extraRoots={controls} />
  </Modal>;
}

// Mounted with the Ant catalogue. The original modules are loaded lazily and
// use non-modal dialog.show(); Ant owns the backdrop, focus and viewport bounds.
export function PackageDialogs() {
  const records = useRef(new Map<HTMLDialogElement, Record>());
  const [dialogs, setDialogs] = useState<Record[]>([]);
  useEffect(() => {
    let next = 0, queued = false, disposed = false;
    const previous = (window as any).LandPPTPackageUI;
    (window as any).LandPPTPackageUI = { openDialog: (dialog: HTMLDialogElement) => dialog.show() };
    function sync() {
      queued = false; if (disposed) return;
      document.querySelectorAll<HTMLDialogElement>('dialog.package-dialog[open]').forEach(node => {
        let record = records.current.get(node);
        if (!record) { record = { node, key: ++next, origin: document.activeElement as HTMLElement, footer: null }; records.current.set(node, record); }
        const footer = node.querySelector<HTMLElement>('footer');
        if (footer) record.footer = footer;
      });
      for (const [node] of records.current) if (!node.isConnected || !node.open) records.current.delete(node);
      setDialogs(Array.from(records.current.values()).map(record => ({ ...record })));
    }
    const observer = new MutationObserver(changes => {
      if (!changes.some(change => !(change.target instanceof Element ? change.target : change.target.parentElement)?.closest('[data-native-ant-host]') && ((change.target instanceof Element ? change.target : change.target.parentElement)?.closest('.package-dialog') || change.type === 'childList'))) return;
      if (!queued) { queued = true; queueMicrotask(sync); }
    });
    observer.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ['open', 'disabled', 'hidden', 'class'] }); sync();
    return () => { disposed = true; observer.disconnect(); (window as any).LandPPTPackageUI = previous; records.current.clear(); };
  }, []);
  return <>{dialogs.map((record, index) => <PackageDialog key={record.key} record={record} index={index} />)}</>;
}
