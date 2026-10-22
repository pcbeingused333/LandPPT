import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Alert, Button, Checkbox, Flex, Form, Input, Modal, Space, Spin, Tabs, Typography } from 'antd';
import { CodeOutlined, ExpandOutlined, EyeOutlined, ReloadOutlined } from '@ant-design/icons';
import type { TemplateWizardController } from '../controllers/template-wizard-controller';
import { modalFocus } from './modal-focus';
import { SlideDocument } from './slide-document';
import './generator-wizard.css';

function TemplatePreview({ html, fullscreen = false }: { html: string; fullscreen?: boolean }) {
  return <div className={`template-wizard-preview${fullscreen ? ' is-fullscreen' : ''}`}>
    {html ? <SlideDocument html={html} title={fullscreen ? '自由模板全屏预览' : '自由模板预览'} contain={fullscreen} interactive={fullscreen} /> : <Typography.Text type="secondary">模板生成后将在这里显示</Typography.Text>}
  </div>;
}

// Keep the existing syntax editor when it is available. Its lifecycle is local
// to this ref; Ant TextArea remains a fully functional fallback without a CDN.
function TemplateCode({ value, disabled, onChange }: { value: string; disabled: boolean; onChange(value: string): void }) {
  const root = useRef<HTMLDivElement>(null);
  const editor = useRef<any>(null);
  const change = useRef(onChange); change.current = onChange;
  useLayoutEffect(() => {
    const textarea = root.current?.querySelector('textarea');
    const CodeMirror = (window as any).CodeMirror;
    if (!textarea || !CodeMirror) return;
    const instance = CodeMirror.fromTextArea(textarea, { mode: 'htmlmixed', theme: 'dracula', lineNumbers: true, lineWrapping: true, autoCloseTags: true, autoCloseBrackets: true, foldGutter: true, gutters: ['CodeMirror-linenumbers', 'CodeMirror-foldgutter'], indentUnit: 2, tabSize: 2 });
    editor.current = instance;
    instance.on('change', () => change.current(instance.getValue()));
    const observer = new ResizeObserver(() => instance.refresh());
    if (root.current) observer.observe(root.current);
    return () => { observer.disconnect(); instance.toTextArea(); editor.current = null; };
  }, []);
  useEffect(() => { if (editor.current && editor.current.getValue() !== value) editor.current.setValue(value); }, [value]);
  useEffect(() => { editor.current?.setOption('readOnly', disabled); }, [disabled]);
  return <div ref={root} className="template-wizard-code"><Input.TextArea aria-label="模板 HTML 源码" value={value} disabled={disabled} onChange={event => onChange(event.target.value)} spellCheck={false} /></div>;
}

export function GeneratorWizard({ controller }: { controller: TemplateWizardController }) {
  const [state, setState] = useState(controller.getSnapshot);
  const [tab, setTab] = useState('preview');
  const [fullscreen, setFullscreen] = useState(false);
  const origin = useRef<HTMLElement | null>(null);
  const wasOpen = useRef(false);
  useEffect(() => controller.subscribe(setState), [controller]);
  useEffect(() => {
    if (state.open && !wasOpen.current) origin.current = document.activeElement as HTMLElement | null;
    if (!state.open && wasOpen.current) { setFullscreen(false); queueMicrotask(() => origin.current?.isConnected && origin.current.focus()); }
    wasOpen.current = state.open;
  }, [state.open]);
  const cancel = () => controller.cancel();
  return <>
    <Modal centered destroyOnHidden open={state.open} title="自由模板 · AI 设计" width={1040} className="template-wizard" onCancel={cancel} mask={{ closable: false }} modalRender={modalFocus}
      footer={<Flex className="template-wizard-footer" justify="space-between" gap={8} wrap><Button onClick={cancel}>取消</Button><Space wrap><Button icon={<ReloadOutlined aria-hidden />} disabled={state.busy || state.blocked} onClick={() => void controller.generate(true)}>重新生成</Button><Button type="primary" loading={state.phase === 'confirming' && state.busy} disabled={state.busy || state.blocked || !state.ready || !state.draft.trim()} onClick={() => void controller.confirm()}>确认并开始生成PPT</Button></Space></Flex>}>
      <div className="template-wizard-layout">
        <section className="template-wizard-design" aria-label="模板设计预览">
          <Tabs activeKey={tab} onChange={setTab} items={[
            { key: 'preview', label: <><EyeOutlined aria-hidden /> 预览</>, children: <TemplatePreview html={state.html} /> },
            { key: 'code', label: <><CodeOutlined aria-hidden /> 源代码</>, children: <><TemplateCode value={state.draft} disabled={state.busy} onChange={controller.editDraft} /><Flex justify="end" style={{ marginTop: 8 }}><Button disabled={state.busy || !state.draft.trim()} onClick={() => { controller.applyDraft(); setTab('preview'); }}>应用到预览</Button></Flex></> },
          ]} tabBarExtraContent={<Button type="text" aria-label="全屏预览模板" icon={<ExpandOutlined aria-hidden />} disabled={!state.html} onClick={() => setFullscreen(true)} />} />
          {state.busy && <Space role="status" aria-live="polite"><Spin size="small" /><Typography.Text>{state.status}</Typography.Text></Space>}
          {!state.busy && <Typography.Paragraph type="secondary" role="status" aria-live="polite">{state.status}</Typography.Paragraph>}
          {state.error && <Alert type="error" showIcon title={state.error} />}
          {state.notice && <Alert type="info" showIcon title={state.notice} />}
          <Button type="link" disabled={state.busy || state.blocked} onClick={() => void controller.check()}>检查后台结果</Button>
        </section>
        <section className="template-wizard-settings" aria-label="模板使用设置">
          <Typography.Title level={5}>确认使用此模板</Typography.Title>
          <Typography.Paragraph type="secondary">先预览和调整模板，确认后开始生成演示文稿。</Typography.Paragraph>
          <Form layout="vertical">
            <Form.Item><Checkbox checked={state.save} disabled={state.busy} onChange={event => controller.setSave(event.target.checked)}>保存到模板库</Checkbox></Form.Item>
            {state.save && <Form.Item label="模板名称" htmlFor="template-wizard-name" extra="名称冲突时会自动添加后缀。"><Input id="template-wizard-name" value={state.name} disabled={state.busy} onChange={event => controller.setName(event.target.value)} /></Form.Item>}
            <Form.Item label="调整要求" htmlFor="template-wizard-adjustment"><Input.TextArea id="template-wizard-adjustment" value={state.adjustment} disabled={state.busy || !state.ready} autoSize={{ minRows: 3, maxRows: 6 }} placeholder="例如：改为蓝色主题，增加留白" onChange={event => controller.setAdjustment(event.target.value)} /></Form.Item>
            <Button block disabled={state.busy || state.blocked || !state.ready || !state.adjustment.trim()} loading={state.phase === 'adjusting' && state.busy} onClick={() => void controller.adjust()}>AI 调整模板</Button>
          </Form>
          <Typography.Paragraph type="secondary" className="template-wizard-hint">源码修改保留在当前页面，点击确认后保存到项目。AI 调整使用服务器保存的模板。</Typography.Paragraph>
        </section>
      </div>
    </Modal>
    <Modal centered destroyOnHidden open={state.open && fullscreen} title="自由模板全屏预览" width="calc(100vw - 32px)" className="template-wizard-fullscreen" footer={null} onCancel={() => setFullscreen(false)} modalRender={modalFocus} zIndex={1100}>
      <TemplatePreview html={state.html} fullscreen />
    </Modal>
  </>;
}
