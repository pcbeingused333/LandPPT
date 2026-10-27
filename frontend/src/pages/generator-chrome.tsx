import { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, App, Badge, Button, Drawer, Dropdown, Progress, Space, Tag, Timeline, Typography } from 'antd';
import { CaretRightOutlined, HistoryOutlined, PauseOutlined, StopOutlined, EditOutlined, PlaySquareOutlined, SettingOutlined } from '@ant-design/icons';
import type { ApiData } from '../api';
import { modalFocus } from '../components/modal-focus';
import { UnattendedPanel } from '../components/unattended';
import { GeneratorWizard } from '../components/generator-wizard';
import { GeneratorPreview } from '../components/generator-preview';
import { ProjectStages, ProjectWorkspaceHeader } from '../components/project-stages';
import { createGeneratorController } from '../controllers/generator-controller';
import { createTemplateWizardController } from '../controllers/template-wizard-controller';
import './generator-chrome.css';

const controls = [
  { id: 'startBtn', label: '开始生成', icon: <CaretRightOutlined aria-hidden /> },
  { id: 'pauseBtn', label: '暂停', icon: <PauseOutlined aria-hidden /> },
  { id: 'resumeBtn', label: '继续', icon: <CaretRightOutlined aria-hidden /> },
  { id: 'stopBtn', label: '停止生成', icon: <StopOutlined aria-hidden /> },
  { id: 'editorBtn', label: '打开编辑器', icon: <EditOutlined aria-hidden /> },
  { id: 'slideshowBtn', label: '幻灯片放映', icon: <PlaySquareOutlined aria-hidden /> },
];

export default function GeneratorChrome({ data, active = true }: { data: ApiData; active?: boolean }) {
  const { modal } = App.useApp();
  const dialogs = useRef(new Set<() => void>());
  const templateController = useMemo(() => createTemplateWizardController({ projectId: data.projectId, ...data.templateInitial, unattended: !!data.unattendedActive }, {
    ask: (text, signal) => ask(text, signal), navigate: path => location.assign(path),
  }), [data, modal]);
  function ask(text: string, signal: AbortSignal) {
    return new Promise<boolean>(resolve => {
      if (signal.aborted) { resolve(false); return; }
      let done = false;
      const finish = (answer: boolean) => { if (done) return; done = true; signal.removeEventListener('abort', cancel); dialogs.current.delete(cancel); resolve(answer); };
      const cancel = () => { finish(false); dialog.destroy(); };
      const dialog = modal.confirm({ title: '操作确认', content: <p className="generator-confirm-text">{text}</p>, okText: '确认', cancelText: '取消', modalRender: modalFocus, onOk: () => finish(true), onCancel: () => finish(false) });
      dialogs.current.add(cancel); signal.addEventListener('abort', cancel, { once: true });
    });
  }
  const controller = useMemo(() => createGeneratorController({ projectId: data.projectId, ...data.generationInitial,
    autoStart: new URLSearchParams(location.search).get('auto_start') === 'true',
    unattended: !!data.unattendedActive, generating: !!data.workspace?.generating,
  }, {
    prepare: templateController.prepare,
    confirm: text => ask(text, new AbortController().signal),
  }), [data, templateController]);
  const [state, setState] = useState(controller.getSnapshot);
  const activeRef = useRef(active); activeRef.current = active;
  useEffect(() => { controller.setVisible(active && !document.hidden); }, [active, controller]);
  const [unattendedStatus, setUnattendedStatus] = useState<string>();
  const [monitorVisible, setMonitorVisible] = useState(!!data.unattendedActive);
  const settingsButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const unsubscribe = controller.subscribe(setState);
    const visibility = () => controller.setVisible(activeRef.current && !document.hidden);
    const hide = () => { templateController.cancel(); controller.suspend(); dialogs.current.forEach(cancel => cancel()); };
    const show = (event: PageTransitionEvent) => { if (event.persisted) controller.resume(); };
    templateController.mount(); controller.setVisible(activeRef.current && !document.hidden); controller.mount();
    document.addEventListener('visibilitychange', visibility);
    window.addEventListener('pagehide', hide); window.addEventListener('pageshow', show);
    return () => {
      unsubscribe(); templateController.dispose(); controller.dispose(); dialogs.current.forEach(cancel => cancel());
      document.removeEventListener('visibilitychange', visibility);
      window.removeEventListener('pagehide', hide); window.removeEventListener('pageshow', show);
    };
  }, [controller, templateController]);
  const packageMode = data.generationMode === 'package';
  const base = `/projects/${encodeURIComponent(data.projectId)}`;
  const connectionStatus = /connected|completed/.test(state.connectionClass) && !/disconnected/.test(state.connectionClass) ? 'success'
    : /error|failed/.test(state.connectionClass) ? 'error' : /paused/.test(state.connectionClass) ? 'warning' : 'default';
  const reloadTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(reloadTimer.current), []);
  // Task record: product-language history of what the controller reported.
  const [log, setLog] = useState<{ key: number; time: string; text: string; color: string }[]>([]);
  const [logOpen, setLogOpen] = useState(false);
  const reported = useRef({ message: '', pages: new Set<number>(), completed: 0, key: 0 });
  useEffect(() => {
    if (!state.visible) return;
    const entries: { text: string; color: string }[] = [];
    const completed = state.completed || 0;
    const newPages = state.slides.filter(slide => (!slide.generation_failed || slide.is_user_edited) && !reported.current.pages.has(slide.page_number));
    for (const slide of newPages) {
      reported.current.pages.add(slide.page_number);
      entries.push({ text: state.total ? `第 ${slide.page_number} / ${state.total} 页已完成` : `第 ${slide.page_number} 页已完成`, color: 'green' });
    }
    if (!newPages.length && completed > reported.current.completed) entries.push({ text: state.total ? `已有 ${completed} / ${state.total} 页可用` : `已有 ${completed} 页可用`, color: 'green' });
    reported.current.completed = Math.max(reported.current.completed, completed);
    if (state.message && state.message !== reported.current.message) { reported.current.message = state.message; entries.push({ text: state.message, color: state.state === 'error' ? 'red' : state.state === 'complete' ? 'green' : 'gray' }); }
    if (!entries.length) return;
    const time = new Date().toLocaleTimeString('zh-CN', { hour12: false });
    const next = entries.map(entry => ({ ...entry, time, key: reported.current.key++ }));
    setLog(previous => [...previous, ...next].slice(-200));
  }, [state.visible, state.message, state.state, state.completed, state.total, state.slides]);
  const running = !!data.unattendedActive || ['running', 'reconnecting', 'paused', 'recovering'].includes(state.phase);
  const manual = !data.unattendedActive;
  const visibleControls = controls.map(control => ({ ...control, label: control.id === 'startBtn' ? state.startLabel : control.label,
    visible: control.id === 'startBtn' ? manual && (state.canStart || state.busy && ['idle', 'error', 'stopped'].includes(state.phase))
      : control.id === 'pauseBtn' ? manual && ['running', 'reconnecting'].includes(state.phase)
      : control.id === 'resumeBtn' ? manual && state.phase === 'paused'
      : control.id === 'stopBtn' ? manual && ['running', 'reconnecting', 'paused', 'recovering'].includes(state.phase)
      : state.slides.length > 0 || state.phase === 'complete',
    disabled: ['startBtn', 'pauseBtn', 'resumeBtn', 'stopBtn'].includes(control.id) && state.busy,
  })).filter(control => control.visible);
  function action(id: string) {
    if (id === 'startBtn') void controller.start();
    else if (id === 'pauseBtn') controller.pause();
    else if (id === 'resumeBtn') void controller.resumeGeneration();
    else if (id === 'stopBtn') void controller.stop();
    else if (id === 'editorBtn' && data.embedded) location.assign(`${base}/edit`);
    else window.open(`${base}/${id === 'editorBtn' ? 'edit' : 'fullscreen'}`, '_blank', 'noopener');
  }
  return <>
    <GeneratorWizard controller={templateController} />
    <section className="main-container generator-workspace generator-ant-workspace" aria-label="幻灯片生成工作区">
    <header className="generator-ant-chrome">
    <ProjectWorkspaceHeader back={{ href: base, label: '返回项目详情' }} title={data.title}
      meta={<Tag>{packageMode ? '快速模式 · 模板包' : '自由设计'}</Tag>}
      actions={<Space wrap size={8}><Space wrap className="generator-ant-actions" role="group" aria-label="幻灯片生成与查看">{visibleControls.map(control => <Button key={control.id} id={`ui-${control.id}`} aria-label={control.label} type={control.id === 'startBtn' || control.id === 'editorBtn' ? 'primary' : 'default'} danger={control.id === 'stopBtn'} disabled={control.disabled} loading={['startBtn', 'resumeBtn'].includes(control.id) && control.disabled} icon={control.icon} onClick={() => action(control.id)}>{control.label}</Button>)}</Space><Dropdown trigger={['click']} onOpenChange={open => { if (!open) queueMicrotask(() => settingsButton.current?.focus()); }} menu={{ items: [
        { key: 'template', label: <a href={`${base}/template-selection?mode=${packageMode ? 'package' : 'freeform'}`}>{packageMode ? '快速模式设置' : '选择模板'}</a> },
        { key: 'mode', label: <a href={`${base}/template-selection?mode=${packageMode ? 'freeform' : 'package'}`}>{packageMode ? '切换到自由设计' : '切换到快速模式'}</a> },
        { key: 'model', label: <a href="/ai-config#jev-config">决策模型配置</a> },
      ] }}><Button ref={settingsButton} icon={<SettingOutlined aria-hidden />}>生成设置</Button></Dropdown></Space>}
      stages={<ProjectStages projectId={data.projectId} state={data.workspace} current="generate" generating={running} />} />
    </header>
    <div className="content-area"><div className="editor-section">
    <div id={active ? "unattendedMonitor" : undefined} hidden={!monitorVisible}>{active && <UnattendedPanel projectId={data.projectId} initiallyActive={!!data.unattendedActive} onUpdate={run => setUnattendedStatus(run.task_status || run.status)} onVisibility={setMonitorVisible} onComplete={run => { setUnattendedStatus(run.task_status || run.status); if (!reloadTimer.current) reloadTimer.current = setTimeout(() => location.reload(), run.task_status === 'completed' ? 1500 : 6000); }} />}</div>
    <div id="generatorStatusUI">{state.notice && <Alert type="warning" showIcon title={state.notice} />}{state.visible && <section className="generator-ant-status" aria-label="生成状态"><div className="generator-ant-status-row"><span role={state.state === 'error' ? 'alert' : 'status'} aria-live="polite">{state.message}</span><Space size={4} className="generator-ant-status-tools"><Badge status={connectionStatus} text={state.connection} /><Button size="small" type="link" icon={<HistoryOutlined aria-hidden />} aria-haspopup="dialog" onClick={() => setLogOpen(true)}>任务记录</Button></Space></div>{state.state !== 'complete' && <Progress percent={state.percent} format={percent => `${Math.round(percent || 0)}%`} strokeColor="var(--lp-primary)" status={state.state === 'error' ? 'exception' : 'normal'} size="small" />}</section>}</div>
    <GeneratorPreview data={data} state={state} unattendedStatus={unattendedStatus} />
    </div></div>
    </section>
    <Drawer title="任务记录" open={logOpen} onClose={() => setLogOpen(false)} size={Math.min(380, window.innerWidth)} className="generator-task-log">
      {log.length ? <Timeline items={[...log].reverse().map(entry => ({ key: entry.key, color: entry.color, content: <><div>{entry.text}</div><Typography.Text type="secondary">{entry.time}</Typography.Text></> }))} /> : <Typography.Paragraph type="secondary">开始生成后，这里会按时间记录每一步进度。</Typography.Paragraph>}
    </Drawer>
  </>;
}
