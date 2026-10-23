import { useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Card, Collapse, Drawer, Flex, Form, Input, Progress, Select, Space, Tag, Timeline, Typography } from 'antd';
import { ReloadOutlined, RobotOutlined, StopOutlined } from '@ant-design/icons';
import { request, type ApiData } from '../api';
import { modalFocus } from './modal-focus';
import { nativeSelectIsOpen } from './native-controls';

export function ProjectAgent({ projectId, disabled = false }: { projectId: string; disabled?: boolean }) {
  const { modal, message } = App.useApp();
  const [open, setOpen] = useState(() => new URLSearchParams(location.search).get('agent') === '1');
  const [instruction, setInstruction] = useState(''), [indices, setIndices] = useState<number[]>([]);
  const [task, setTask] = useState<ApiData | null>(null), [error, setError] = useState('');
  const [scope, setScope] = useState<ApiData | null>(null);
  const scopeRevision = useRef('');
  const [loading, setLoading] = useState(false), [pending, setPending] = useState(false), [refresh, setRefresh] = useState(0);
  const trigger = useRef<HTMLButtonElement>(null), locked = useRef(false), mounted = useRef(true);
  const endpoint = `/api/projects/${encodeURIComponent(projectId)}/agent`;
  const active = !!task && ['pending', 'queued', 'running'].includes(task.status);
  const result = task?.result || {};
  const changes: ApiData[] = Array.isArray(result.pages) ? result.pages : [];
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController(); let timer: ReturnType<typeof setTimeout>;
    setLoading(true); setError('');
    async function poll() {
      try {
        const value = await request(endpoint, 'GET', undefined, controller.signal);
        if (controller.signal.aborted) return;
        if (!value.context || typeof value.context.revision !== 'string' || !Array.isArray(value.context.pages)) throw new Error('项目页面范围不完整，请刷新重试');
        if (value.context.revision !== scopeRevision.current) { if (scopeRevision.current) void message.info('项目已更新，请重新选择页面范围；要求草稿已保留'); setScope(value.context); scopeRevision.current = value.context.revision; setIndices([]); }
        setTask(value.task); setError(''); setLoading(false);
        if (value.task && ['pending', 'queued', 'running'].includes(value.task.status)) timer = setTimeout(poll, 1200);
      } catch (reason) { if (!controller.signal.aborted) { setError((reason as Error).message); setLoading(false); } }
    }
    void poll(); return () => { controller.abort(); clearTimeout(timer); };
  }, [open, endpoint, refresh, message]);
  async function start() {
    if (locked.current || !instruction.trim() || active || loading || !scope) return;
    locked.current = true; setPending(true); setError('');
    try {
      const value = await request(endpoint, 'POST', { instruction: instruction.trim(), indices, project_revision: scope.revision, previous_task_id: task?.task_id || undefined });
      if (mounted.current) { setTask({ task_id: value.task_id, status: 'pending', result: {} }); setRefresh(value => value + 1); }
    } catch (reason) { if (mounted.current) setError((reason as Error).message); }
    finally { locked.current = false; if (mounted.current) setPending(false); }
  }
  async function cancel() {
    if (locked.current || !task) return;
    locked.current = true; setPending(true);
    try { await request(`${endpoint}/${encodeURIComponent(task.task_id)}/cancel`, 'POST'); if (mounted.current) setRefresh(value => value + 1); }
    catch (reason) { if (mounted.current) setError((reason as Error).message); }
    finally { locked.current = false; if (mounted.current) setPending(false); }
  }
  function apply() {
    modal.confirm({ title: `应用这 ${changes.length} 页修改？`, content: '将更新页面画面。任一页面冲突时整批不保存；大纲和讲稿保持原内容。', okText: '确认应用', cancelText: '继续检查', modalRender: modalFocus,
      onOk: async () => {
        if (locked.current || !task) return;
        locked.current = true; setPending(true); setError('');
        try { await request(`${endpoint}/${encodeURIComponent(task.task_id)}/apply`, 'POST'); if (mounted.current) { setRefresh(value => value + 1); void message.success('跨页修改已保存，重新打开编辑器可查看'); } }
        catch (reason) { if (mounted.current) setError((reason as Error).message); throw reason; }
        finally { locked.current = false; if (mounted.current) setPending(false); }
      },
    });
  }
  return <>
    <Button ref={trigger} icon={<RobotOutlined aria-hidden />} disabled={disabled} onClick={() => setOpen(true)}>项目助手</Button>
    <Drawer title="项目助手" open={open} size={760} styles={{ wrapper: { maxWidth: '100vw' } }} onClose={() => { if (!pending) setOpen(false); }} closable={!pending} maskClosable={!pending} keyboard={!pending}
      afterOpenChange={value => { if (!value) trigger.current?.focus(); }}
      drawerRender={node => <div style={{ height: '100%' }} onKeyDown={event => { event.stopPropagation(); if (event.key === 'Escape' && !nativeSelectIsOpen(event.target) && !pending) setOpen(false); if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') event.preventDefault(); }}>{modalFocus(node, { height: '100%' })}</div>}
      footer={<Flex justify="space-between" gap={8} wrap><Button icon={<ReloadOutlined aria-hidden />} disabled={pending || loading} onClick={() => setRefresh(value => value + 1)}>刷新任务</Button><Space wrap>{active ? <Button icon={<StopOutlined aria-hidden />} loading={pending} disabled={task?.cancel_requested} onClick={() => void cancel()}>{task?.cancel_requested ? '正在停止' : '停止任务'}</Button> : <Button type="primary" loading={pending} disabled={loading || !instruction.trim()} onClick={() => void start()}>发送请求</Button>}</Space></Flex>}>
      <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
        <Alert showIcon type="info" title="检查项目或修改所选页面" description="修改先生成预览，确认后保存。使用编辑模型，分析按轮、页面编辑按页沿用 AI 编辑计费；停止前已完成的调用仍计费。" />
        <Form layout="vertical" disabled={active || pending || loading}>
          <Form.Item label="允许读取与修改的页面（最多 10 页）" extra="未选择页面时可以询问项目状态与结构；页面正文仅在所选范围内读取。">
            <Select aria-label="项目助手页面范围" mode="multiple" virtual={false} maxCount={10} value={indices} onChange={setIndices} placeholder="选择本次操作范围" options={(scope?.pages || []).map((page: ApiData) => ({ value: page.index, label: `第 ${page.index + 1} 页 · ${page.title || '未命名'}` }))} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="你的要求"><Input.TextArea aria-label="项目助手要求" rows={4} maxLength={8000} showCount value={instruction} onChange={event => setInstruction(event.target.value)} placeholder="例如：检查所选页的内容重复；将所选页的表达精简为面向管理层的版本。" /></Form.Item>
        </Form>
        {error && <Alert type="error" showIcon title="操作未完成" description={error} />}
        {task && <Card size="small" title="本次任务" extra={<Tag>{active ? '进行中' : task.status === 'completed' ? '已完成' : task.status === 'cancelled' ? '已停止' : '失败'}</Tag>}>
          <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{task.instruction}</Typography.Paragraph>
          {active && <Progress percent={Math.min(99, Number(task.progress) || 0)} />}
          {Array.isArray(result.steps) && <Timeline items={result.steps.map((step: string, index: number) => ({ key: index, content: step }))} />}
          {task.error && <Alert showIcon type="error" title={task.error} description={result.error} />}
          {result.summary && <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{result.summary}</Typography.Paragraph>}
          {result.link && /^\/(projects\/[^?#]+\/(todo|edit|fullscreen)|image-gallery\?tab=sources&project=)/.test(result.link) && <Button href={result.link}>前往相关页面</Button>}
        </Card>}
        {!!changes.length && <>
          <Typography.Title level={5}>逐页修改预览</Typography.Title>
          <Collapse items={changes.map(page => ({ key: page.slide_index, label: `第 ${page.slide_index + 1} 页 · ${page.title || '未命名'}`, children: <><Typography.Paragraph>{page.summary}</Typography.Paragraph><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 360, overflow: 'auto' }}>{page.diff || '页面画面已修改'}</pre></> }))} />
          {result.applied ? <Alert showIcon type="success" title="这批修改已保存" /> : <Button block type="primary" loading={pending} disabled={active || loading || task?.status !== 'completed' || task?.cancel_requested} onClick={apply}>应用 {changes.length} 页修改</Button>}
        </>}
      </Space>
    </Drawer>
  </>;
}
