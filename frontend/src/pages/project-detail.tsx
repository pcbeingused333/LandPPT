import { useRef, useState } from 'react';
import { Alert, App, Button, Card, Collapse, Descriptions, Dropdown, Form, Input, Modal, Progress, Select, Space, Tag, Tooltip } from 'antd';
import { ArrowLeftOutlined, ArrowUpOutlined, ArrowDownOutlined, CopyOutlined, DeleteOutlined, DownloadOutlined, EditOutlined, EyeOutlined, RobotOutlined, UnorderedListOutlined, AppstoreOutlined, PlusOutlined, MoreOutlined, InboxOutlined, FileTextOutlined, CheckCircleOutlined, ClockCircleOutlined, DashboardOutlined } from '@ant-design/icons';
import { request, type ApiData } from '../api';
import { modalFocus } from '../components/modal-focus';
import { projectPath, projectStates } from '../components/projects';
import { navigatePage } from '../navigation';

type Confirmation = { kind: 'archive' | 'delete' | 'restore' | 'slide-delete'; version?: number; index?: number; final?: boolean };
const text = (value: unknown) => typeof value === 'string' ? value : value == null ? '' : JSON.stringify(value, null, 2);
const slideType = (value: string) => ({ title: '封面', content: '内容', conclusion: '总结' } as Record<string, string>)[value] || value;
const parseOutline = (value: string): ApiData => {
  const outline = JSON.parse(value);
  if (!outline || typeof outline !== 'object' || Array.isArray(outline)) throw new Error('大纲必须是 JSON 对象');
  return outline;
};

export default function ProjectDetail({ data }: { data: ApiData }) {
  const { message } = App.useApp();
  const project = data.project;
  const base = projectPath(project);
  const [outline, setOutline] = useState<ApiData | null>(project.outline);
  const slides: ApiData[] = Array.isArray(outline?.slides) ? outline.slides : [];
  const [detailed, setDetailed] = useState(false);
  const [view, setView] = useState<number | null>(null);
  const [edit, setEdit] = useState<'outline' | number | null>(null);
  const [json, setJson] = useState('');
  const [editorError, setEditorError] = useState('');
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [optimizing, setOptimizing] = useState(false);
  const [optimizeOpen, setOptimizeOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const locked = useRef(false);
  const optimizeTrigger = useRef<HTMLButtonElement>(null);
  const projectMenuTrigger = useRef<HTMLButtonElement>(null);
  const confirmationTrigger = useRef<HTMLElement | null>(null);
  const [slideForm] = Form.useForm();
  const [optimizeForm] = Form.useForm();
  const [dragOver, setDragOver] = useState<number | null>(null);

  async function run(action: () => Promise<void>, editor = false) {
    if (locked.current) return;
    locked.current = true; setPending(true); setEditorError('');
    try { await action(); }
    catch (error) { const value = (error as Error).message; if (editor) setEditorError(value); else message.error(value); }
    finally { locked.current = false; setPending(false); }
  }
  async function persist(next: ApiData, operation?: ApiData) {
    await request(`${base}/update-outline`, 'POST', { outline_content: JSON.stringify(next, null, 2), ...(operation ? { operation } : {}) });
    setOutline(next); location.reload();
  }
  function move(from: number, to: number) {
    if (!outline || !Number.isInteger(from) || from < 0 || from >= slides.length || to < 0 || to >= slides.length || from === to) return;
    const next = [...slides]; const [slide] = next.splice(from, 1); next.splice(to, 0, slide);
    run(() => persist({ ...outline, slides: next.map((item, index) => ({ ...item, page_number: index + 1 })) }, { type: 'move', slide_index: from, to_index: to }));
  }
  function confirmSlideDelete(index: number) {
    if (slides.length <= 1) { message.warning('至少保留一页幻灯片'); return; }
    confirmationTrigger.current = document.querySelector(`[aria-label="第 ${index + 1} 页更多操作"]`);
    setConfirmation({ kind: 'slide-delete', index });
  }
  function confirmAction() {
    if (!confirmation || pending) return;
    if (confirmation.kind === 'delete' && !confirmation.final) { setConfirmation({ ...confirmation, final: true }); return; }
    run(async () => {
      switch (confirmation.kind) {
        case 'archive': await request(`/api${base}/archive`, 'POST'); navigatePage('/projects'); break;
        case 'delete': await request(`/api/database/projects/${encodeURIComponent(project.project_id)}`, 'DELETE'); navigatePage('/projects'); break;
        case 'restore': await request(`/api${base}/versions/${confirmation.version}/restore`, 'POST'); location.reload(); break;
        case 'slide-delete': {
          const next = slides.filter((_, index) => index !== confirmation.index).map((slide, index) => ({ ...slide, page_number: index + 1 }));
          await persist({ ...outline, slides: next }, { type: 'delete', slide_index: confirmation.index }); break;
        }
      }
      setConfirmation(null);
    });
  }
  function openEditor(target: 'outline' | number) {
    setEditorError(''); setEdit(target);
    if (target === 'outline') setJson(JSON.stringify(outline, null, 2));
    else {
      const slide = slides[target];
      slideForm.setFieldsValue({ title: slide.title || '', subtitle: slide.subtitle || '', slide_type: slide.slide_type || 'content', content_points: Array.isArray(slide.content_points) ? [...slide.content_points] : [], content: text(slide.content) });
    }
  }
  async function saveEditor() {
    if (pending || optimizing) return;
    if (edit === 'outline') {
      let next: ApiData;
      try { next = parseOutline(json); } catch (error) { setEditorError(`JSON 格式错误：${(error as Error).message}`); return; }
      await run(() => persist(next), true);
    } else if (typeof edit === 'number') {
      let values: ApiData;
      try { values = await slideForm.validateFields(); } catch { return; }
      const points = (values.content_points || []).map((point: string) => point.trim()).filter(Boolean);
      const next = [...slides];
      next[edit] = { ...next[edit], title: values.title.trim(), subtitle: values.subtitle?.trim() || undefined, slide_type: values.slide_type,
        content_points: points.length ? points : undefined, content: values.content?.trim() || undefined };
      await run(() => persist({ ...outline, slides: next }), true);
    }
  }
  async function openOptimize() {
    if (edit === 'outline') {
      try { parseOutline(json); } catch { setEditorError('请先修正大纲 JSON 格式'); return; }
    } else { try { await slideForm.validateFields(['title']); } catch { return; } }
    optimizeForm.resetFields(); setOptimizeOpen(true);
  }
  async function optimize() {
    if (locked.current) return;
    let values: ApiData;
    try { values = await optimizeForm.validateFields(); } catch { return; }
    if (locked.current) return;
    locked.current = true; setOptimizing(true); setEditorError('');
    try {
      const current = edit === 'outline' ? parseOutline(json) : outline!;
      const metadata = current.metadata || {};
      const audience = metadata.target_audience === '自定义' && metadata.custom_audience ? metadata.custom_audience : metadata.target_audience || '普通大众';
      const result = await request('/api/ai/optimize-outline', 'POST', {
        outline_content: edit === 'outline' ? json : JSON.stringify(current), user_request: values.requirements.trim(), language: metadata.language || 'zh',
        project_info: { topic: current.title || '未知', scenario: metadata.scenario || '通用', target_audience: audience },
        optimization_type: edit === 'outline' ? 'full' : 'single', ...(typeof edit === 'number' ? { slide_index: edit } : {}),
      });
      if (!result.success || !result.optimized_content) throw new Error(result.error || 'AI 未返回可用结果');
      if (edit === 'outline') { parseOutline(result.optimized_content); setJson(result.optimized_content); }
      else {
        const slide = parseOutline(result.optimized_content);
        slideForm.setFieldsValue({ title: slide.title || '', subtitle: slide.subtitle || '', slide_type: slide.slide_type || 'content', content_points: Array.isArray(slide.content_points) ? slide.content_points : [] });
      }
      setOptimizeOpen(false); message.success('AI 优化完成，请检查后保存');
    } catch (error) { message.error((error as Error).message); }
    finally { locked.current = false; setOptimizing(false); }
  }
  function exportJson() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(outline, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a'); link.href = url; link.download = `${outline?.title || 'ppt_outline'}_${new Date().toISOString().slice(0, 10)}.json`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const state = projectStates[project.status] || ['异常状态', 'error'];
  const activeStage = data.board?.stages.find((stage: ApiData) => stage.status === 'running') || data.board?.stages.find((stage: ApiData) => stage.status === 'pending');
  const confirmationCopy = confirmation?.kind === 'archive' ? ['归档项目', '归档后项目将不会显示在活跃项目列表中。', '归档']
    : confirmation?.kind === 'restore' ? [`恢复到 v${confirmation.version}`, '当前未保存的更改将丢失。', '恢复']
      : confirmation?.kind === 'slide-delete' ? ['删除大纲页面', `确定删除第 ${confirmation.index! + 1} 页大纲吗？对应幻灯片也会同步删除。`, '删除']
        : confirmation?.final ? ['再次确认删除项目', '所有项目数据将永久丢失，此操作不可撤销。', '删除'] : ['确认删除项目', '确定要删除这个项目吗？此操作不可撤销。', '继续'];
  const tools = (index: number) => <Space size={2} className="outline-slide-actions">
    <Tooltip title="查看详情"><Button type="text" aria-label="查看详情" icon={<EyeOutlined aria-hidden />} onClick={() => setView(index)} /></Tooltip>
    <Tooltip title="编辑"><Button type="text" disabled={pending} aria-label="编辑此页" icon={<EditOutlined aria-hidden />} onClick={() => openEditor(index)} /></Tooltip>
    <Dropdown trigger={['click']} placement="bottomRight" menu={{ items: [
      { key: 'up', label: '上移', icon: <ArrowUpOutlined aria-hidden />, disabled: pending || index === 0 },
      { key: 'down', label: '下移', icon: <ArrowDownOutlined aria-hidden />, disabled: pending || index === slides.length - 1 },
      { type: 'divider' }, { key: 'delete', label: '删除此页', icon: <DeleteOutlined aria-hidden />, danger: true, disabled: pending },
    ], onClick: ({ key }) => key === 'delete' ? confirmSlideDelete(index) : move(index, index + (key === 'up' ? -1 : 1)) }}>
      <Button type="text" disabled={pending} aria-label={`第 ${index + 1} 页更多操作`} icon={<MoreOutlined aria-hidden />} />
    </Dropdown>
  </Space>;
  const points = (slide: ApiData) => Array.isArray(slide.content_points) && slide.content_points.length ? <ul>{slide.content_points.map((point: unknown, index: number) => <li key={index}>{text(point)}</li>)}</ul> : <p className="outline-content">{text(slide.content) || '暂无内容'}</p>;
  return <div className="project-detail-page">
    <nav className="detail-breadcrumb" aria-label="面包屑"><a href="/projects">项目列表</a><span aria-hidden>/</span><span>项目详情</span></nav>
    <div className="page-heading project-detail-hero"><div className="detail-title-group">
      <Tooltip title="返回项目列表"><Button href="/projects" aria-label="返回项目列表" icon={<ArrowLeftOutlined aria-hidden />} /></Tooltip>
      <div><h1>{project.title}</h1><p><Tag color={state[1]} icon={project.status === 'completed' ? <CheckCircleOutlined aria-hidden /> : <ClockCircleOutlined aria-hidden />}>{state[0]}</Tag><span>项目 ID：<code>{project.project_id}</code></span></p></div>
    </div><Space className="detail-project-actions" size={8}>
      {project.status === 'in_progress' && data.board && <Button type="primary" icon={<UnorderedListOutlined aria-hidden />} href={`${base}/todo`}>查看 TODO 看板</Button>}
      {project.status === 'completed' && project.hasSlides && <><Button type="primary" icon={<EyeOutlined aria-hidden />} href={`${base}/fullscreen`} target="_blank" rel="noopener">预览 PPT</Button><Tooltip title="打开编辑器"><Button href={`${base}/edit`} aria-label="打开编辑器" icon={<EditOutlined aria-hidden />} /></Tooltip></>}
      <Dropdown trigger={['click']} placement="bottomRight" menu={{ items: [
        { key: 'archive', label: '归档项目', icon: <InboxOutlined aria-hidden /> }, { key: 'copy', label: '复制项目', icon: <CopyOutlined aria-hidden /> },
        { type: 'divider' }, { key: 'delete', label: '删除项目', icon: <DeleteOutlined aria-hidden />, danger: true },
      ], onClick: ({ key }) => {
        if (key === 'copy') run(async () => { const result = await request(`/api${base}/duplicate`, 'POST'); if (result.status !== 'success' || !result.project_id) throw new Error('复制失败'); navigatePage(`/projects/${encodeURIComponent(result.project_id)}`); });
        else { confirmationTrigger.current = projectMenuTrigger.current; setConfirmation({ kind: key === 'archive' ? 'archive' : 'delete' }); }
      } }} disabled={pending}><Button ref={projectMenuTrigger} disabled={pending} aria-label="项目更多操作" icon={<MoreOutlined aria-hidden />} /></Dropdown>
    </Space></div>
    <div className={`detail-overview${data.board ? ' detail-overview--with-progress' : ''}`}>
      <Card size="small" title={<span className="detail-card-title"><FileTextOutlined aria-hidden />项目信息</span>} className="detail-info-card" extra={<span className="detail-version-badge">v{project.version}</span>}>
        {project.status === 'in_progress' && <p className="subtle">{activeStage ? `${activeStage.name} · ${activeStage.status === 'running' ? '正在执行' : '等待开始'}` : '正在处理中'}</p>}
        <Descriptions size="small" column={{ xs: 1, sm: 2 }} items={[
          { key: 'topic', label: '主题', children: project.topic, span: 2 }, { key: 'scenario', label: '场景', children: project.scenario },
          { key: 'created', label: '创建时间', children: project.created },
          ...(project.requirements ? [{ key: 'requirements', label: '特殊要求', children: project.requirements, span: 2 }] : []),
        ]} />
      </Card>
      {data.board && <Card size="small" title={<span className="detail-card-title"><DashboardOutlined aria-hidden />进度概览</span>} className="detail-progress-card"><div className="detail-progress-summary"><div><strong>{project.status === 'completed' ? '演示文稿已就绪' : activeStage?.name || '等待下一阶段'}</strong><p className="subtle">{data.board.stages.filter((stage: ApiData) => stage.status === 'completed').length} / {data.board.stages.length} 个阶段已完成</p></div><span>{data.board.progress}<small>%</small></span></div><Progress percent={data.board.progress} size="small" showInfo={false} strokeColor={project.status === 'completed' ? '#389e0d' : '#111'} /><Collapse ghost className="detail-stage-list" defaultActiveKey={project.status === 'completed' ? [] : ['stages']} items={[{
        key: 'stages', label: <span>阶段状态 <span className="subtle">{data.board.stages.length} 个阶段</span></span>, children: data.board.stages.map((stage: ApiData) => <div key={stage.id} className="stage-row">
          <div className="stage-info"><strong>{stage.name}</strong><p className="stage-description">{stage.description}</p>{stage.status === 'running' && <Progress size="small" percent={stage.progress} />}</div>
          {stage.status === 'completed' ? <Tag color="success" icon={<CheckCircleOutlined aria-hidden />}>已完成</Tag> : <Button size="small" href={`${base}/todo`} danger={stage.status === 'failed'}>{stage.status === 'running' ? '查看进度' : stage.status === 'failed' ? '重试' : stage.id === 'outline_generation' ? '生成大纲' : stage.id === 'ppt_creation' ? '生成PPT' : '开始'}</Button>}
        </div>),
      }]} /></Card>}
    </div>
    {outline && <section className="outline-panel">
      <div className="section-heading"><h2>PPT 大纲</h2><Space size={4}>
        {!!slides.length && <Tooltip title={detailed ? '简洁视图' : '详细视图'}><Button aria-label={`切换为${detailed ? '简洁' : '详细'}视图`} icon={detailed ? <AppstoreOutlined aria-hidden /> : <UnorderedListOutlined aria-hidden />} onClick={() => setDetailed(!detailed)} /></Tooltip>}
        <Tooltip title="编辑大纲"><Button disabled={pending} aria-label="编辑大纲" icon={<EditOutlined aria-hidden />} onClick={() => openEditor('outline')} /></Tooltip>
        <Tooltip title="导出 JSON"><Button aria-label="导出 JSON" icon={<DownloadOutlined aria-hidden />} onClick={exportJson} /></Tooltip>
      </Space></div>
      <div className="outline-surface"><div className="outline-summary"><h3>{outline.title || project.topic || '未命名大纲'}</h3>{!!slides.length && <span className="detail-outline-count">{slides.length} 页</span>}<span className="subtle">拖拽排序 · 更多菜单中可上移、下移</span><span className="subtle">场景：{outline.metadata?.scenario || project.scenario} · 语言：{outline.metadata?.language || 'zh'}</span>{outline.metadata?.target_audience && <span className="subtle">受众：{outline.metadata.target_audience === '自定义' ? outline.metadata.custom_audience : outline.metadata.target_audience}</span>}</div>
        {slides.length ? <div id={detailed ? 'detailView' : 'compactView'} className={`outline-grid${detailed ? ' outline-grid--detail' : ''}`}>{slides.map((slide, index) => <Card key={index} size="small" className={`outline-slide-card${dragOver === index ? ' is-drag-over' : ''}`} draggable={!pending} onDragStart={event => { event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', String(index)); }} onDragOver={event => { event.preventDefault(); setDragOver(index); }} onDragLeave={() => setDragOver(null)} onDragEnd={() => setDragOver(null)} onDrop={event => { event.preventDefault(); setDragOver(null); move(Number.parseInt(event.dataTransfer.getData('text/plain'), 10), index); }}>
          <div className="outline-card-top"><span className="outline-page-number">{String(slide.page_number || index + 1).padStart(2, '0')}</span>{tools(index)}</div><h3>{slide.title || '未命名幻灯片'}</h3>{slide.subtitle && <p className="subtle">{slide.subtitle}</p>}
          {detailed ? points(slide) : <p className="outline-excerpt">{text(slide.content_points?.[0] || slide.content) || '暂无内容'}</p>}
          <div className="outline-card-meta">{slide.slide_type && <Tag>{slideType(slide.slide_type)}</Tag>}{slide.content_points?.length > 1 && <span className="subtle">{slide.content_points.length} 个要点</span>}</div>
        </Card>)}</div> : <Card size="small"><pre className="detail-legacy-content">{text(outline.content) || '大纲内容正在生成中…'}</pre></Card>}
      </div>
    </section>}
    {!!data.versions.length && <section className="detail-versions"><div className="section-heading"><h2>版本历史</h2></div><Card size="small">{data.versions.map((version: ApiData) => <div className="detail-version-row" key={version.version}><strong>v{version.version}</strong><div className="detail-version-info"><span>{version.description}</span><p className="subtle">{version.timestamp}</p></div><Button disabled={pending} onClick={event => { confirmationTrigger.current = event.currentTarget; setConfirmation({ kind: 'restore', version: version.version }); }}>恢复此版本</Button></div>)}</Card></section>}
    <div className="detail-navigation"><a href="/dashboard"><DashboardOutlined aria-hidden /> 项目仪表板</a><span className="subtle">项目 ID：{project.project_id}</span></div>
    <Modal title={confirmationCopy[0]} open={!!confirmation} modalRender={modalFocus} focusTriggerAfterClose={false} afterClose={() => confirmationTrigger.current?.focus()} onCancel={() => { if (!pending) setConfirmation(null); }} onOk={confirmAction} confirmLoading={pending} okText={confirmationCopy[2]} cancelText="取消" okButtonProps={{ danger: confirmation?.kind === 'delete' || confirmation?.kind === 'slide-delete' }}>{confirmationCopy[1]}</Modal>
    <Modal title={view == null ? '' : `第 ${view + 1} 页详情`} open={view != null} modalRender={modalFocus} onCancel={() => setView(null)} footer={<Button onClick={() => setView(null)}>关闭</Button>} destroyOnHidden>{view != null && <><h3>{slides[view].title}</h3><p className="subtle">{slides[view].subtitle}</p>{points(slides[view])}{slides[view].slide_type && <Tag>类型：{slideType(slides[view].slide_type)}</Tag>}</>}</Modal>
    <Modal title={edit === 'outline' ? '编辑 PPT 大纲' : `编辑第 ${Number(edit) + 1} 页`} width={760} open={edit != null} modalRender={modalFocus} onCancel={() => { if (!pending && !optimizing) setEdit(null); }} destroyOnHidden footer={<div className="outline-editor-footer"><Button ref={optimizeTrigger} disabled={pending || optimizing} icon={<RobotOutlined aria-hidden />} onClick={openOptimize}>{edit === 'outline' ? '优化大纲' : 'AI 优化'}</Button><Space><Button disabled={pending || optimizing} onClick={() => setEdit(null)}>取消</Button><Button type="primary" loading={pending} disabled={optimizing} onClick={saveEditor}>保存修改</Button></Space></div>}>
      {editorError && <Alert type="error" showIcon title={editorError} className="page-error" />}
      {edit === 'outline' ? <Input.TextArea aria-label="大纲 JSON" value={json} disabled={pending || optimizing} onChange={event => setJson(event.target.value)} rows={16} className="outline-json-editor" /> : <Form form={slideForm} layout="vertical" disabled={pending || optimizing} className="slide-edit-form">
        <Form.Item name="title" label="标题" rules={[{ required: true, whitespace: true, message: '请输入幻灯片标题' }]}><Input aria-label="标题" /></Form.Item><Form.Item name="subtitle" label="副标题"><Input /></Form.Item>
        <Form.Item name="slide_type" label="幻灯片类型"><Select options={[{ value: 'content', label: '内容页' }, { value: 'title', label: '标题页' }, { value: 'conclusion', label: '结论页' }, ...(typeof edit === 'number' && slides[edit]?.slide_type && !['content', 'title', 'conclusion'].includes(slides[edit].slide_type) ? [{ value: slides[edit].slide_type, label: slides[edit].slide_type }] : [])]} /></Form.Item>
        <Form.List name="content_points">{(fields, { add, remove }) => <div className="outline-points"><label>内容要点</label>{fields.map((field, index) => <div className="outline-point" key={field.key}><Form.Item {...field} noStyle><Input aria-label={`要点 ${index + 1}`} /></Form.Item><Button danger type="text" aria-label={`删除要点 ${index + 1}`} icon={<DeleteOutlined aria-hidden />} onClick={() => remove(field.name)} /></div>)}<Button icon={<PlusOutlined aria-hidden />} onClick={() => add('')}>添加要点</Button></div>}</Form.List>
        <Form.Item name="content" label="内容"><Input.TextArea rows={4} /></Form.Item>
      </Form>}
    </Modal>
    <Modal title={edit === 'outline' ? 'AI 优化大纲' : `AI 优化第 ${Number(edit) + 1} 页`} open={optimizeOpen} modalRender={modalFocus} onCancel={() => { if (!optimizing) setOptimizeOpen(false); }} onOk={optimize} confirmLoading={optimizing} okText="开始优化" cancelText="取消" afterClose={() => optimizeTrigger.current?.focus()}>
      <p className="subtle">优化结果会显示在编辑窗口中，检查后点击“保存修改”。</p><Form form={optimizeForm} layout="vertical" disabled={optimizing}><Form.Item name="requirements" label="优化要求" rules={[{ required: true, whitespace: true, message: '请输入优化要求' }]}><Input.TextArea rows={4} placeholder="例如：简化内容，突出核心要点" /></Form.Item></Form>
    </Modal>
  </div>;
}
