import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Alert, App, Button, Drawer, Dropdown, Grid, Modal, Segmented, Space, Tag } from 'antd';
import { ArrowLeftOutlined, BarsOutlined, CodeOutlined, DownloadOutlined, EditOutlined, EllipsisOutlined, EyeOutlined, PlayCircleOutlined, ReloadOutlined, RobotOutlined, SaveOutlined } from '@ant-design/icons';
import type { ApiData } from '../api';
import { useNativeFeedback } from '../components/native-feedback';
import { modalFocus } from '../components/modal-focus';
import { NativeControls, keepNativeSubmitForms, nativeSelectIsOpen } from '../components/native-controls';
import { editorTaskNotice, EditorTaskPanel } from '../components/editor-task-progress';
import { EditorThumbnailMenu, type EditorContextMenu } from '../components/editor-thumbnail-menu';
import { EditorExportDialog, type EditorExportProgress } from '../components/editor-export-dialog';
import { EditorShareDialog, type EditorShareLinks } from '../components/editor-share-dialog';
import { EditorQuickIcons } from '../components/editor-quick-icons';
import { EditorDocumentSidebar } from '../components/editor-document-sidebar';
import { createEditorController } from '../controllers/editor-controller';
import '../components/native-surfaces.css';
import './slides-editor.css';

type DialogRecord = { key: number; node: HTMLElement; type: string[]; title: string; closable: boolean; origin: HTMLElement | null; footer?: HTMLElement | null; exportProgress?: EditorExportProgress; shareLinks?: EditorShareLinks };
type EditorState = ApiData & { dialogs: DialogRecord[]; toasts: ApiData[]; contextMenu: EditorContextMenu | null };
type Controller = ReturnType<typeof createEditorController>;

// Keep the exact native form nodes/listeners; Ant owns their bounded frame.
function NativeNodes({ nodes }: { nodes: Node[] }) {
  const target = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const origins = nodes.map(node => ({ node, parent: node.parentNode, next: node.nextSibling }));
    keepNativeSubmitForms(nodes);
    nodes.forEach(node => target.current?.appendChild(node));
    return () => origins.forEach(({ node, parent, next }) => { if (parent && node.isConnected) parent.insertBefore(node, next?.parentNode === parent ? next : null); });
  }, [nodes]);
  return <div className="editor-adapted-content" ref={target} />;
}

function EditorDialog({ record, index, tasks, controller }: { record: DialogRecord; index: number; tasks: ApiData[]; controller: Controller }) {
  const nativeDialog = record.node.tagName === 'DIALOG';
  const canvas = record.node.id === 'svg-page-editor';
  const [parts] = useState(() => ({ content: nativeDialog ? [record.node] : Array.from(record.node.childNodes), footer: !canvas && record.type[3] ? record.node.querySelector<HTMLElement>(record.type[3]) : null }));
  const footer = record.footer || parts.footer;
  const footerNodes = useMemo<Node[]>(() => footer ? [footer] : [], [footer]);
  const controlRoots = useMemo<HTMLElement[]>(() => footer ? [footer] : [], [footer]);
  useLayoutEffect(() => {
    const node = record.node, oldRole = node.getAttribute('role'), oldModal = node.getAttribute('aria-modal');
    node.classList.add(nativeDialog ? 'editor-ant-native-dialog' : 'editor-ant-modal-host');
    node.setAttribute('role', 'presentation'); node.removeAttribute('aria-modal');
    return () => {
      node.classList.remove('editor-ant-native-dialog', 'editor-ant-modal-host');
      if (oldRole) node.setAttribute('role', oldRole); else node.removeAttribute('role');
      if (oldModal) node.setAttribute('aria-modal', oldModal);
      const origin = record.origin;
      queueMicrotask(() => { if (!document.querySelector('.editor-ant-dialog') && origin?.isConnected && origin.getClientRects().length) origin.focus(); });
    };
  }, [record.node, nativeDialog]);
  return <Modal open aria-label={record.title} title={canvas ? null : record.title} footer={footer ? <NativeNodes nodes={footerNodes} /> : null}
    width={Number(record.type[4])} zIndex={2000 + index * 20} className={`editor-ant-dialog${canvas ? ' editor-ant-canvas' : ''}`}
    getContainer={nativeDialog ? undefined : () => record.node} closable={!canvas && record.closable} keyboard={!canvas && record.closable}
    mask={{ closable: !canvas && record.closable }} onCancel={() => controller.close(record)} modalRender={node => <div onKeyDownCapture={event => { if (event.key === 'Escape' && !canvas && !nativeSelectIsOpen(event.target)) { event.preventDefault(); event.stopPropagation(); if (record.closable) controller.close(record); } }}>{modalFocus(node)}</div>}>
    <EditorTaskPanel tasks={tasks} />
    <NativeNodes nodes={parts.content} />
    {!canvas && <NativeControls root={record.node} extraRoots={controlRoots} />}
  </Modal>;
}

function NativeAssistant() {
  const [node] = useState(() => document.getElementById('aiEditSidebar')!);
  const nodes = useRef<Node[]>([node]);
  return <><NativeNodes nodes={nodes.current} /><NativeControls root={node} /></>;
}

export default function SlidesEditor({ data }: { data: ApiData }) {
  useNativeFeedback();
  const { notification } = App.useApp(); const screens = Grid.useBreakpoint();
  const controller = useMemo(() => createEditorController((window as any).LandPPTEditorEngine, (window as any).LandPPTEditorSurfaces), []);
  const [state, setState] = useState<EditorState>(() => controller.getSnapshot() as EditorState);
  const saving = !!state.savePending || !!state.saving;
  const previousToasts = useRef(new Map<string, string>()); const moreRef = useRef<HTMLButtonElement>(null);
  const taskDialog = [...state.dialogs].reverse().find(record => record.node.querySelector('.speech-modal-body-preview'));
  useLayoutEffect(() => {
    // Stage speech shells before the observer/React handoff can paint legacy UI.
    document.body.classList.add('editor-ant-dialogs-ready');
    return () => { document.body.classList.remove('editor-ant-dialogs-ready'); };
  }, []);
  useEffect(() => {
    const unsubscribe = controller.subscribe(value => setState(value as EditorState));
    const hide = () => controller.suspend();
    const show = (event: PageTransitionEvent) => { if (event.persisted) controller.resume(); };
    controller.mount();
    window.addEventListener('pagehide', hide); window.addEventListener('pageshow', show);
    return () => { unsubscribe(); controller.dispose(); window.removeEventListener('pagehide', hide); window.removeEventListener('pageshow', show); };
  }, [controller]);
  useLayoutEffect(() => {
    const resize = () => {
      const quickToolbar = document.getElementById('quickEditToolbar');
      const tools = document.getElementById('editorAntToolbar');
      const pane = document.querySelector('.editor-content');
      if (quickToolbar && tools && pane) {
        const width = quickToolbar.getBoundingClientRect().width, rect = pane.getBoundingClientRect();
        const center = Math.max(8 + width / 2, Math.min(rect.left + rect.width / 2, window.innerWidth - 8 - width / 2));
        quickToolbar.style.setProperty('--quick-toolbar-center', `${center}px`);
        quickToolbar.style.setProperty('--quick-toolbar-top', `${Math.max(8, Math.min(tools.getBoundingClientRect().bottom + 8, window.innerHeight - quickToolbar.offsetHeight - 8))}px`);
        (pane as HTMLElement).style.setProperty('--editor-quick-toolbar-height', `${quickToolbar.offsetHeight}px`);
      }
      const wrapper = document.getElementById('slideFrameWrapper');
      if (wrapper && wrapper.clientWidth > 20 && wrapper.clientHeight > 20) controller.call('applyMainFrameScale');
      controller.call('applyThumbnailPreviewScaleToAll'); controller.call('resizeCodeMirror');
    };
    const observer = new ResizeObserver(resize);
    const pane = document.querySelector('.editor-content'); if (pane) observer.observe(pane);
    const sidebar = document.getElementById('slidesSidebar'); if (sidebar) observer.observe(sidebar);
    const wrapper = document.getElementById('slideFrameWrapper'); if (wrapper) observer.observe(wrapper);
    const quickToolbar = document.getElementById('quickEditToolbar'); if (quickToolbar) observer.observe(quickToolbar);
    const frame = requestAnimationFrame(resize);
    return () => { observer.disconnect(); cancelAnimationFrame(frame); };
  }, []);
  useEffect(() => {
    const keys = new Map<string, string>();
    (taskDialog ? [] : state.toasts).forEach(toast => {
      const signature = JSON.stringify(toast); keys.set(toast.key, signature);
      if (previousToasts.current.get(toast.key) !== signature) notification.open({ key: toast.key, ...editorTaskNotice(toast), duration: 0, closable: false, placement: 'bottomRight' });
    });
    previousToasts.current.forEach((_, key) => { if (!keys.has(key)) notification.destroy(key); }); previousToasts.current = keys;
  }, [state.toasts, taskDialog?.key, notification]);
  useEffect(() => () => { previousToasts.current.forEach((_, key) => notification.destroy(key)); }, [notification]);
  const save = () => { void controller.save(); };
  const call = (name: string, ...args: unknown[]) => controller.call(name, ...args);
  const items = [
    ...(state.clientExport ? [{ key: 'client', label: '客户端导出 PPTX · Beta', onClick: () => call('exportSlidesToPptxClient') }] : []),
    ...(state.nativeExport ? [{ key: 'native', label: 'SVG 原生对象 PPTX', onClick: () => call('exportSvgPagesToPptx', 'native') }] : []),
    ...(state.vectorExport ? [{ key: 'vector', label: 'SVG 矢量保真 PPTX', onClick: () => call('exportSvgPagesToPptx', 'vector') }] : []),
    ...(data.standardExport ? [{ key: 'standard', label: '标准导出 PPTX', onClick: () => call('exportToPPTX') }] : []),
    { key: 'images', label: '图片形式 PPTX', onClick: () => call('exportToPPTXAsImages') },
    { key: 'pdf', label: '导出 PDF', onClick: () => call('exportToPDF') }, { key: 'html', label: '下载 HTML', onClick: () => call('downloadHTML') },
  ];
  const toolbar = <div className="editor-ant-toolbar" role="toolbar" aria-label="幻灯片编辑工具">
    <div className="editor-ant-view"><Segmented aria-label="编辑视图" value={state.mode === 'quickedit' ? 'preview' : state.mode} options={[
      { value: 'preview', label: '预览', icon: <EyeOutlined aria-hidden /> }, { value: 'edit', label: '代码', icon: <CodeOutlined aria-hidden /> }, { value: 'split', label: '分屏' },
    ]} onChange={mode => call('setMode', mode)} /><Button disabled={!state.count} type={state.mode === 'quickedit' ? 'primary' : 'default'} icon={<EditOutlined aria-hidden />} onClick={() => call('toggleQuickEditMode')}>{state.svg ? '编辑 SVG' : '快速编辑'}</Button>{state.packageContent && <Button onClick={() => controller.call('openPackageEditor')}>内容与版式</Button>}</div>
    <Space wrap size={8} className="editor-ant-actions"><Button disabled={!state.count} icon={<PlayCircleOutlined aria-hidden />} onClick={() => controller.call('startSlideshow')}>放映</Button><Button type="primary" disabled={!state.count || state.documentPanel !== 'slides' && !state.documentDirty} loading={saving || state.documentSaving} icon={<SaveOutlined aria-hidden />} onClick={save}>{state.documentPanel === 'outline' ? '保存大纲' : state.documentPanel === 'speech' ? '保存讲稿' : '保存'}</Button><Button disabled={!state.count} icon={<RobotOutlined aria-hidden />} onClick={() => controller.call('openAIEditSidebar')}>AI 编辑</Button>
      <Dropdown trigger={['click']} menu={{ items: [
        { key: 'current', label: '重新生成当前页', onClick: () => call('quickRegenerateSlide') }, { key: 'selected', label: `重新生成所选页（${state.selected}）`, onClick: () => call('regenerateSelectedSlides') }, { key: 'all', label: '重新生成全部', danger: true, onClick: () => call('regenerateAllSlides') },
      ] }}><Button disabled={!state.count} icon={<ReloadOutlined aria-hidden />}>重新生成</Button></Dropdown>
      <Dropdown trigger={['click']} menu={{ items }}><Button data-editor-export-trigger disabled={!state.count} icon={<DownloadOutlined aria-hidden />}>导出</Button></Dropdown>
      <Dropdown trigger={['click']} onOpenChange={open => { if (!open) queueMicrotask(() => moreRef.current?.focus()); }} menu={{ items: [
        { key: 'template', label: '更换模板', onClick: () => call('showChangeTemplateDialog') }, { key: 'share', label: '分享链接', onClick: () => call('showShareDialog') }, { key: 'speech', label: '生成演讲稿', onClick: () => call('showSpeechScriptDialog') }, { key: 'chat', label: '自由对话（当前页）', disabled: state.svg, onClick: () => call('openNativeChatDialog') },
      ] }}><Button ref={moreRef} aria-label="更多工具" icon={<EllipsisOutlined aria-hidden />} /></Dropdown>
    </Space>
  </div>;
  return <>
    <EditorQuickIcons />
    {state.commandError && createPortal(<Alert type="error" showIcon title={state.commandError} />, document.getElementById('editorAntToolbar')!)}
    {createPortal(<EditorDocumentSidebar projectId={String(data.projectId)} pages={state.documentPages} current={state.current} selected={state.selected} dialogCount={state.dialogs.length} bridge={controller} />, document.getElementById('editorAntSidebar')!)}
    <EditorThumbnailMenu state={state.contextMenu} run={controller.runContextAction} dismiss={controller.dismissContextMenu} />
    {createPortal(<header className="editor-ant-header"><Button aria-label="展开或收起幻灯片列表" aria-expanded={state.sidebar} aria-controls="slidesSidebar" icon={<BarsOutlined aria-hidden />} onClick={() => controller.call('toggleSidebar')} /><div className="editor-ant-title"><h1 title={data.title}>{data.title}</h1><span>{state.count ? `第 ${state.current + 1} / ${state.count} 页` : "暂无幻灯片"}{state.svg && <Tag>SVG</Tag>}</span></div><Button href={`/projects/${encodeURIComponent(String(data.projectId))}`} icon={<ArrowLeftOutlined aria-hidden />}>返回项目</Button></header>, document.getElementById('editorAntHeader')!)}
    {createPortal(toolbar, document.getElementById('editorAntToolbar')!)}
    <Drawer title={<Space>AI 编辑助手<Tag>第 {state.current + 1} 页</Tag></Space>} open={state.aiOpen} onClose={() => call('closeAIEditSidebar')} zIndex={1500} size={screens.xs ? '100%' : Math.min(state.aiWidth || 480, window.innerWidth)} className="editor-ant-assistant" forceRender
      extra={<Space size={4}><Button aria-label="查看当前页大纲" onClick={() => call('showSlideOutline')}>大纲</Button>{data.autoRepair && <Button onClick={() => call('autoRepairSlideLayout')}>修复排版</Button>}<Button aria-label="一键配图" onClick={() => call('autoGenerateSlideImages')}>配图</Button></Space>}>
      <NativeAssistant />
    </Drawer>
    {state.dialogs.map((record, index) => record.node.id === 'exportOverlay'
      ? <EditorExportDialog key={record.key} record={record} index={index} projectTitle={data.title} cancel={controller.cancelExport} dismiss={controller.dismissExport} />
      : record.shareLinks ? <EditorShareDialog key={record.key} record={record} index={index} projectTitle={data.title} run={action => controller.runShareAction(record, action)} dismiss={() => controller.close(record)} />
      : <EditorDialog key={record.key} controller={controller} record={record} index={index} tasks={record.key === taskDialog?.key ? state.toasts : []} />)}
  </>;
}
