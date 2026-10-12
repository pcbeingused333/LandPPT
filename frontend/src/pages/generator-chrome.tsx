import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Badge, Button, Dropdown, Progress, Space } from 'antd';
import { ArrowLeftOutlined, CaretRightOutlined, PauseOutlined, StopOutlined, EditOutlined, PlaySquareOutlined, SettingOutlined } from '@ant-design/icons';
import type { ApiData } from '../api';
import { useNativeFeedback } from '../components/native-feedback';
import { UnattendedPanel } from '../components/unattended';
import { GeneratorWizard } from '../components/generator-wizard';
import { GeneratorPreview } from '../components/generator-preview';

const controls = [
  { id: 'startBtn', label: '开始生成', icon: <CaretRightOutlined aria-hidden /> },
  { id: 'pauseBtn', label: '暂停', icon: <PauseOutlined aria-hidden /> },
  { id: 'resumeBtn', label: '继续', icon: <CaretRightOutlined aria-hidden /> },
  { id: 'stopBtn', label: '停止生成', icon: <StopOutlined aria-hidden /> },
  { id: 'editorBtn', label: '打开编辑器', icon: <EditOutlined aria-hidden /> },
  { id: 'slideshowBtn', label: '幻灯片放映', icon: <PlaySquareOutlined aria-hidden /> },
];

// The existing controller owns generation, cancellation, reconnection and
// template preparation. Its inert DOM is an adapter; React reads it and forwards
// clicks, without writing generation state or touching presentation contents.
function snapshot() {
  const status = document.getElementById('generationStatus');
  const connection = document.getElementById('connectionStatus');
  const value = Number.parseFloat(document.getElementById('generationProgress')?.style.width || '0');
  return {
    buttons: controls.map(control => {
      const element = document.getElementById(control.id) as HTMLButtonElement | null;
      return { ...control, visible: !!element && element.style.display !== 'none', disabled: !element || element.disabled, label: element?.textContent?.trim() || control.label };
    }),
    visible: !!status && status.style.display !== 'none',
    message: document.getElementById('statusMessage')?.textContent || '',
    state: status?.dataset.state || '',
    percent: Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : 0,
    connection: connection?.textContent?.trim() || '',
    connectionClass: connection?.className || '',
    total: status?.dataset.totalSlides ? Number(status.dataset.totalSlides) : undefined,
    completed: status?.dataset.completedSlides ? Number(status.dataset.completedSlides) : undefined,
    activePages: (status?.dataset.activePages || '').split(',').map(Number).filter(number => number > 0),
  };
}

export default function GeneratorChrome({ data }: { data: ApiData }) {
  useNativeFeedback();
  const [state, setState] = useState(snapshot);
  const [unattendedStatus, setUnattendedStatus] = useState<string>();
  const settingsButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const source = document.getElementById('generatorControlState');
    if (!source) return;
    const observer = new MutationObserver(() => setState(snapshot()));
    observer.observe(source, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ['style', 'class', 'disabled', 'data-state', 'data-total-slides', 'data-completed-slides', 'data-active-pages'] });
    setState(snapshot());
    return () => observer.disconnect();
  }, []);
  const packageMode = data.generationMode === 'package';
  const base = `/projects/${encodeURIComponent(data.projectId)}`;
  const connectionStatus = /connected|completed/.test(state.connectionClass) && !/disconnected/.test(state.connectionClass) ? 'success'
    : /error|failed/.test(state.connectionClass) ? 'error' : /paused/.test(state.connectionClass) ? 'warning' : 'default';
  const statusTarget = document.getElementById('generatorStatusUI');
  const monitorTarget = document.getElementById('unattendedMonitor');
  const reloadTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(reloadTimer.current), []);
  const visibleControls = state.buttons.filter(control => control.visible
    && (!data.unattendedActive || !['startBtn', 'pauseBtn', 'resumeBtn', 'stopBtn'].includes(control.id))
    && (state.state !== 'error' || !['pauseBtn', 'resumeBtn', 'stopBtn'].includes(control.id)));
  return <>
    <GeneratorWizard />
    <GeneratorPreview data={data} state={state} unattendedStatus={unattendedStatus} />
    {monitorTarget && createPortal(<UnattendedPanel projectId={data.projectId} initiallyActive={!!data.unattendedActive} onUpdate={run => setUnattendedStatus(run.task_status || run.status)} onVisibility={visible => { monitorTarget.hidden = !visible; }} onComplete={run => { setUnattendedStatus(run.task_status || run.status); if (!reloadTimer.current) reloadTimer.current = setTimeout(() => location.reload(), run.task_status === 'completed' ? 1500 : 6000); }} />, monitorTarget)}
    <div className="generator-ant-heading"><Button href="/projects" aria-label="返回项目列表" icon={<ArrowLeftOutlined aria-hidden />} /><div className="generator-ant-title"><span>生成工作区</span><h1 title={data.title}>{data.title}</h1></div><Space wrap className="generator-ant-actions" role="group" aria-label="幻灯片生成与查看">{visibleControls.map(control => <Button key={control.id} id={`ui-${control.id}`} aria-label={control.label} type={control.id === 'startBtn' || control.id === 'editorBtn' ? 'primary' : 'default'} danger={control.id === 'stopBtn'} disabled={control.disabled} loading={control.id === 'startBtn' && control.disabled} icon={control.icon} onClick={() => document.getElementById(control.id)?.click()}>{control.label}</Button>)}</Space></div>
    <div className="generator-ant-mode"><p><strong>{packageMode ? '快速模式 · 模板包' : '自由设计'}</strong><span>{packageMode ? '编写内容，自动匹配模板版式' : '逐页设计内容与风格'}</span></p><Dropdown trigger={['click']} onOpenChange={open => { if (!open) queueMicrotask(() => settingsButton.current?.focus()); }} menu={{ items: [
      { key: 'template', label: <a href={`${base}/template-selection?mode=${packageMode ? 'package' : 'freeform'}`}>{packageMode ? '快速模式设置' : '选择模板'}</a> },
      { key: 'mode', label: <a href={`${base}/template-selection?mode=${packageMode ? 'freeform' : 'package'}`}>{packageMode ? '切换到自由设计' : '切换到快速模式'}</a> },
      { key: 'model', label: <a href="/ai-config#jev-config">决策模型配置</a> },
    ] }}><Button ref={settingsButton} icon={<SettingOutlined aria-hidden />}>生成设置</Button></Dropdown></div>
    {statusTarget && createPortal(state.visible ? <section className="generator-ant-status" aria-label="生成状态"><div className="generator-ant-status-row"><span role={state.state === 'error' ? 'alert' : 'status'} aria-live="polite">{state.message}</span><Badge status={connectionStatus} text={state.connection} /></div>{state.state !== 'complete' && <Progress percent={state.percent} format={percent => `${Math.round(percent || 0)}%`} strokeColor="#111" status={state.state === 'error' ? 'exception' : 'normal'} size="small" />}</section> : null, statusTarget)}
  </>;
}
