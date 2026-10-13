import { useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Card, Collapse, Progress, Space, Tag } from 'antd';
import { RobotOutlined, StopOutlined, ReloadOutlined } from '@ant-design/icons';
import { errorText, request, type ApiData } from '../api';
import { modalFocus } from './modal-focus';
import { progressPercent } from '../progress';

type Monitor = { refresh(): void; destroy(): void; stopped: boolean };
type Options = { container: HTMLElement; projectId: string; initiallyActive: boolean; onRender(run: ApiData | null): void; onError(error: Error): void; onUpdate(run: ApiData): void; onComplete(run: ApiData): void };
const terminal = ['completed', 'failed', 'cancelled'];
const labels: Record<string, string> = { running: '运行中', pending: '等待中', queued: '排队中', completed: '已完成', failed: '已失败', cancelled: '已取消', skipped: '未选择' };
const display = (value: unknown) => value == null ? '' : typeof value === 'string' ? value : errorText(value);

export function UnattendedPanel({ projectId, initiallyActive, onUpdate, onComplete, onVisibility }: { projectId: string; initiallyActive: boolean; onUpdate?: (run: ApiData) => void; onComplete?: (run: ApiData) => void; onVisibility?: (visible: boolean) => void }) {
  const [run, setRun] = useState<ApiData | null>(null);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState(false);
  const [pending, setPending] = useState(false);
  const callbacks = useRef({ onUpdate, onComplete, onVisibility }); callbacks.current = { onUpdate, onComplete, onVisibility };
  const monitor = useRef<Monitor | null>(null);
  const confirming = useRef(false);
  const failed = useRef(false);
  const { modal, message } = App.useApp();
  useEffect(() => {
    const factory = (window as typeof window & { UnattendedMonitor?: { mount(options: Options): Monitor } }).UnattendedMonitor;
    if (!factory) { setError('任务监控未加载，请刷新页面后重试。'); callbacks.current.onVisibility?.(true); return; }
    const instance = factory.mount({ container: document.createElement('div'), projectId, initiallyActive,
      onRender: value => {
        setRun(value); setError('');
        callbacks.current.onVisibility?.(!!value);
        if (value?.task_status === 'failed' && !failed.current) setExpanded(true);
        failed.current = value?.task_status === 'failed';
      },
      onError: () => { setError('任务状态读取失败，稍后会自动重试。'); callbacks.current.onVisibility?.(true); },
      onUpdate: value => callbacks.current.onUpdate?.(value), onComplete: value => callbacks.current.onComplete?.(value),
    });
    monitor.current = instance;
    return () => { instance.destroy(); monitor.current = null; };
  }, [projectId, initiallyActive]);
  function stop() {
    if (confirming.current || pending || !run || terminal.includes(run.task_status)) return;
    confirming.current = true;
    modal.confirm({ title: '停止无人值守任务', content: '当前阶段结束后停止，已生成的内容会保留。', okText: '确认停止', cancelText: '取消', okButtonProps: { danger: true }, modalRender: modalFocus,
      afterClose: () => { confirming.current = false; },
      onOk: async () => {
        setPending(true);
        try {
          await request(`/api/projects/${encodeURIComponent(projectId)}/unattended/cancel`, 'POST');
          message.info('已请求停止，当前阶段结束后生效');
          if (monitor.current) { monitor.current.stopped = false; monitor.current.refresh(); }
        } catch (reason) { message.error('停止失败：' + (reason as Error).message); throw reason; }
        finally { setPending(false); }
      },
    });
  }
  if (!run && !error) return null;
  const stages: ApiData[] = Array.isArray(run?.stages) ? run.stages : [];
  const planned = stages.filter(stage => stage.status !== 'skipped');
  const done = planned.filter(stage => stage.status === 'completed').length;
  const current = planned.find(stage => stage.status === 'running');
  const state = run?.task_status || run?.status || 'pending';
  const active = !!run && !terminal.includes(state);
  const percent = progressPercent(run?.overall_progress);
  return <Card size="small" className="unattended-ant" title={<h2><RobotOutlined aria-hidden /> 无人值守任务</h2>} extra={<Space wrap><Tag color={state === 'failed' ? 'error' : state === 'completed' ? 'success' : 'default'}>{labels[run?.status || state] || display(run?.status || state)}</Tag>{active && <Button danger icon={<StopOutlined aria-hidden />} aria-label="停止无人值守任务" disabled={pending} onClick={stop}>停止</Button>}{run?.download_url && <Button href={run.download_url}>下载视频</Button>}</Space>}>
    {error && <Alert type="warning" title={error} action={<Button icon={<ReloadOutlined aria-hidden />} onClick={() => monitor.current?.refresh()}>重试</Button>} />}
    {run && <><p className="unattended-ant-topic" title={display(run.topic)}>{active && current ? `正在${display(current.name || current.id)} · 第 ${done + 1}/${planned.length} 步` : display(run.topic)}</p><Progress size="small" percent={percent} strokeColor="#111" status={state === 'failed' ? 'exception' : 'normal'} aria-label="任务总进度" />
      {run.error && state !== 'cancelled' && <Alert type="error" title={display(run.error)} className="unattended-ant-error" />}
      <Collapse size="small" activeKey={expanded ? ['stages'] : []} onChange={keys => setExpanded(keys.includes('stages'))} items={[{ key: 'stages', label: `阶段详情 · ${done}/${planned.length} 已完成`, children: <><ol className="unattended-ant-stages">{planned.map((stage, index) => <li key={`${stage.id}-${index}`}><div><strong>{display(stage.name || stage.id)}</strong><Tag color={stage.status === 'failed' ? 'error' : stage.status === 'completed' ? 'success' : 'default'}>{labels[stage.status] || display(stage.status)}</Tag></div>{(stage.error || stage.message) && <p className={stage.error ? 'unattended-ant-error' : 'subtle'}>{display(stage.error || stage.message)}</p>}</li>)}</ol>{stages.length > planned.length && <p className="subtle">另有 {stages.length - planned.length} 个阶段未选择，不会执行</p>}</> }]} />
    </>}
  </Card>;
}
