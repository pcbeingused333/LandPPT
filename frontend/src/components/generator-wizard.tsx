import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Button, Modal } from 'antd';
import { NativeControls, NativeNodes } from './native-controls';
import { modalFocus } from './modal-focus';
import './native-surfaces.css';

function Wizard({ root, onClose }: { root: HTMLElement; onClose: () => void }) {
  const [content] = useState<Node[]>(() => [root.querySelector('.ftm-body')!]);
  const [footer] = useState<Node[]>(() => [root.querySelector('.ftm-btn-group')!]);
  const origin = useRef(document.activeElement as HTMLElement | null);
  useLayoutEffect(() => {
    root.classList.add('generator-ant-modal-host');
    const resize = new ResizeObserver(() => { (window as any).updateFreeTemplatePreviewScale?.(); (window as any).freeTemplateCodeMirror?.refresh(); });
    resize.observe(root.querySelector('#freeTemplatePreviewContainer')!);
    return () => { resize.disconnect(); root.classList.remove('generator-ant-modal-host'); queueMicrotask(() => origin.current?.isConnected && origin.current.focus()); };
  }, [root]);
  return <Modal open getContainer={() => root} width={1040} title="自由模板 · AI 设计" className="generator-ant-wizard package-ant-modal" mask={{ closable: false }} onCancel={onClose}
    footer={<div className="generator-wizard-actions"><Button onClick={onClose}>取消</Button><NativeNodes nodes={footer} /></div>} modalRender={modalFocus}>
    <NativeNodes nodes={content} /><NativeControls root={root} />
  </Modal>;
}

export function GeneratorWizard() {
  const root = document.getElementById('freeTemplateModal');
  const [open, setOpen] = useState(root?.dataset.antOpen === 'true');
  useEffect(() => {
    if (!root) return;
    const observer = new MutationObserver(() => setOpen(root.dataset.antOpen === 'true'));
    observer.observe(root, { attributes: true, attributeFilter: ['data-ant-open'] });
    setOpen(root.dataset.antOpen === 'true'); return () => observer.disconnect();
  }, [root]);
  const close = () => (window as any).LandPPTGeneratorUI.createModal(root).hide();
  return open && root ? <Wizard root={root} onClose={close} /> : null;
}
