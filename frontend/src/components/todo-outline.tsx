import { useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Card, Empty, Form, Input, Modal, Select, Space, Spin, Tabs, Tag } from 'antd';
import { DeleteOutlined, DownloadOutlined, EditOutlined, EyeOutlined, PlusOutlined, ReloadOutlined, RobotOutlined } from '@ant-design/icons';
import { request, type ApiData } from '../api';
import { modalFocus } from './modal-focus';
import { type OutlineController, type OutlineState } from '../controllers/outline-controller';
import { createOutlineStreamView } from '../controllers/outline-stream-view';

const text = (value: unknown) => typeof value === 'string' ? value : value == null ? '' : JSON.stringify(value);
function parseOutline(value: string): ApiData {
  const outline = JSON.parse(value);
  if (!outline || Array.isArray(outline) || !Array.isArray(outline.slides) || !outline.slides.length || outline.slides.some((slide: unknown) => !slide || typeof slide !== 'object' || Array.isArray(slide))) throw new Error('大纲必须是 JSON 对象，并包含至少一页 slides。');
  if (outline.slides.some((slide: ApiData) => slide.content_points != null && !Array.isArray(slide.content_points))) throw new Error('每页 content_points 必须是数组。');
  return outline;
}

export function TodoOutline({ projectId, unattendedActive, readOnly, controller }: { projectId: string; unattendedActive: boolean; readOnly: boolean; controller: OutlineController }) {
  const { message, modal } = App.useApp();
  const [state, setState] = useState<OutlineState>(() => controller.snapshot());
  const [tab, setTab] = useState('outline'); const [detailed, setDetailed] = useState(false);
  const [view, setView] = useState<number | null>(null); const [edit, setEdit] = useState<'json' | number | null>(null);
  const [json, setJson] = useState(''); const [editorError, setEditorError] = useState('');
  const [pending, setPending] = useState(false); const [optimizing, setOptimizing] = useState(false);
  const [optimizeOpen, setOptimizeOpen] = useState(false); const [optimizeError, setOptimizeError] = useState('');
  const [regenerateOpen, setRegenerateOpen] = useState(false); const [requirements, setRequirements] = useState('');
  const [slideForm] = Form.useForm(); const [optimizeForm] = Form.useForm();
  const locked = useRef(false); const aiTrigger = useRef<HTMLButtonElement>(null);
  const original = useRef<ApiData>({});
  const streamNode = useRef<HTMLDivElement>(null), jumpButton = useRef<HTMLButtonElement>(null);
  const outline = state.outline; const slides: ApiData[] = outline?.slides || [];
  const disabled = state.loading || unattendedActive || readOnly || pending || optimizing;
  useEffect(() => {
    return controller.subscribe(setState);
  }, [controller]);
  useEffect(() => {
    if (!streamNode.current || !jumpButton.current) return;
    const view = createOutlineStreamView(streamNode.current, jumpButton.current);
    const unsubscribe = controller.subscribeStream(view.setStream);
    return () => { unsubscribe(); view.destroy(); };
  }, [controller]);
  function openEditor(kind: 'json' | number) {
    if (!outline) return;
    original.current = outline; setEditorError(''); setEdit(kind);
    if (kind === 'json') setJson(JSON.stringify(outline, null, 2));
    else slideForm.setFieldsValue({ title: text(slides[kind].title), subtitle: text(slides[kind].subtitle), description: text(slides[kind].description), slide_type: slides[kind].slide_type || slides[kind].type || 'content', content_points: Array.isArray(slides[kind].content_points) ? slides[kind].content_points.map(text) : [] });
  }
  async function draft() {
    if (edit === 'json') return parseOutline(json);
    const fields = await slideForm.validateFields();
    const points = (fields.content_points || []).map((point: string) => String(point || '').trim()).filter(Boolean);
    if (!points.length) throw new Error('至少需要一个内容要点。');
    const index = Number(edit), previous = original.current.slides[index];
    const slide = { ...previous, page_number: previous.page_number || index + 1, title: fields.title.trim(), content_points: points, slide_type: fields.slide_type, type: fields.slide_type };
    for (const key of ['subtitle', 'description']) { if (fields[key]?.trim()) slide[key] = fields[key].trim(); else delete slide[key]; }
    return { ...original.current, slides: original.current.slides.map((item: ApiData, i: number) => i === index ? slide : item) };
  }
  async function save() {
    if (locked.current) return;
    locked.current = true; setPending(true); setEditorError('');
    try {
      const next = await draft();
      await request(`/projects/${encodeURIComponent(projectId)}/update-outline`, 'POST', { outline_content: JSON.stringify(next, null, 2) });
      controller.saved(next); setEdit(null); message.success('大纲修改已保存');
    } catch (error) { if (!(error as ApiData).errorFields) setEditorError((error as Error).message); }
    finally { locked.current = false; setPending(false); }
  }
  async function openOptimize() {
    try { await draft(); setOptimizeError(''); optimizeForm.resetFields(); setOptimizeOpen(true); }
    catch (error) { if (!(error as ApiData).errorFields) setEditorError((error as Error).message); }
  }
  async function optimize() {
    if (locked.current) return;
    let fields: ApiData;
    try { fields = await optimizeForm.validateFields(); } catch { return; }
    locked.current = true; setOptimizing(true); setOptimizeError('');
    try {
      const current = await draft(), metadata = current.metadata || {};
      const result = await request('/api/ai/optimize-outline', 'POST', {
        outline_content: JSON.stringify(current, null, 2), user_request: fields.requirements.trim(),
        language: state.language || metadata.language || current.language || 'zh',
        project_info: { topic: current.title || '未知', scenario: metadata.scenario || '通用', target_audience: metadata.target_audience === '自定义' && metadata.custom_audience ? metadata.custom_audience : metadata.target_audience || '普通大众' },
        optimization_type: edit === 'json' ? 'full' : 'single', ...(typeof edit === 'number' ? { slide_index: edit } : {}),
      });
      if (!result.success || !result.optimized_content) throw new Error(result.error || 'AI 没有返回优化内容。');
      if (edit === 'json') setJson(JSON.stringify(parseOutline(result.optimized_content), null, 2));
      else {
        const next = JSON.parse(result.optimized_content);
        if (!next || Array.isArray(next) || typeof next !== 'object' || !Array.isArray(next.content_points)) throw new Error('AI 返回的页面格式不正确，请重试。');
        slideForm.setFieldsValue({ title: next.title || '', subtitle: next.subtitle || '', description: next.description || '', slide_type: next.slide_type || next.type || 'content', content_points: next.content_points.map(text) });
      }
      setOptimizeOpen(false); message.success('优化结果已填入编辑窗口，请检查后保存。');
    } catch (error) { setOptimizeError((error as Error).message); }
    finally { locked.current = false; setOptimizing(false); }
  }
  function exportJson() {
    if (!outline) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(outline, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a'); link.href = url; link.download = `${outline.title || 'ppt_outline'}_${new Date().toISOString().slice(0, 10)}.json`;
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  async function regenerate() {
    if (locked.current || state.loading || unattendedActive || readOnly) return;
    locked.current = true; setPending(true); setRegenerateOpen(false);
    try { await controller.regenerate(requirements.trim()); }
    finally { locked.current = false; setPending(false); }
  }
  function startPpt() {
    modal.confirm({ title: '操作确认', content: '确认开始生成PPT？这将跳转到模板选择页面。', okText: '确认', cancelText: '取消', modalRender: modalFocus,
      onOk: () => { const url = controller.templateSelectionUrl(); if (url) location.assign(url); },
    });
  }
  const points = (slide: ApiData) => <>{Array.isArray(slide.content_points) && slide.content_points.length > 0 && <ul className="todo-outline-points">{slide.content_points.map((point: unknown, index: number) => <li key={index}>{text(point)}</li>)}</ul>}{slide.content && <p className="todo-outline-body">{text(slide.content)}</p>}{slide.description && <p className="subtle">{text(slide.description)}</p>}</>;
  const typeOptions = [['title','标题页'],['content','内容页'],['conclusion','结论页'],['thankyou','感谢页']];
  const currentType = Form.useWatch('slide_type', slideForm);
  if (currentType && !typeOptions.some(([value]) => value === currentType)) typeOptions.push([currentType, currentType]);
  return <section className="todo-outline-ant" hidden={!state.visible} aria-label="PPT 大纲工作区">
    <Card size="small" title="PPT 大纲" extra={<Space wrap><Button disabled={disabled} icon={<ReloadOutlined aria-hidden />} onClick={() => setRegenerateOpen(true)}>重新生成</Button><Button disabled={disabled || !outline} icon={<EditOutlined aria-hidden />} onClick={() => openEditor('json')}>编辑 JSON</Button><Button aria-label="导出大纲 JSON" disabled={!outline || state.loading} icon={<DownloadOutlined aria-hidden />} onClick={exportJson}>导出</Button></Space>}>
      {state.error && <Alert showIcon type="error" title="大纲生成失败" description={state.error} className="page-error" />}
      {state.phase === 'recovering' && <Alert showIcon type="warning" title="连接暂时中断" description={state.statusText} className="page-error" />}
      <div hidden={!state.loading} className="todo-outline-stream">
        <div className="todo-outline-stream-heading"><Space><Spin size="small" /><strong>{state.phase === 'recovering' ? '正在获取后台结果' : '正在生成大纲'}</strong></Space><Button ref={jumpButton} data-outline-stream-jump-btn hidden>回到最新</Button></div>
        {state.phase !== 'recovering' && <p className="subtle" role="status">{state.statusText || '实时显示生成结果，完成后可编辑与确认。'}</p>}
        <div ref={streamNode} data-outline-stream-preview className="outline-stream-shell-content" aria-label="大纲实时输出" />
      </div>
      {outline && <><div className="todo-outline-summary"><h2>{text(outline.title) || '未命名大纲'}</h2><span className="subtle">{slides.length} 页 · {text(outline.metadata?.scenario) || '通用'} · {state.language || 'zh'}</span></div>
        <Tabs activeKey={tab} onChange={setTab} tabBarExtraContent={tab === 'outline' && <Button onClick={() => setDetailed(!detailed)}>{detailed ? '简洁视图' : '详细视图'}</Button>} items={[
          { key: 'outline', label: '大纲预览', children: <div className="todo-outline-grid">{slides.map((slide, index) => <Card size="small" key={index} className="todo-outline-slide"><div className="todo-outline-slide-top"><Tag>第 {text(slide.page_number || index + 1)} 页</Tag><Space size={4}><Button aria-label={`查看第 ${index + 1} 页`} icon={<EyeOutlined aria-hidden />} onClick={() => setView(index)} /><Button aria-label={`编辑第 ${index + 1} 页`} disabled={disabled} icon={<EditOutlined aria-hidden />} onClick={() => openEditor(index)} /></Space></div><h3>{text(slide.title) || '未命名幻灯片'}</h3>{slide.subtitle && <p className="subtle">{text(slide.subtitle)}</p>}{detailed ? points(slide) : <p className="outline-excerpt">{text(slide.content_points?.[0] || slide.content) || '暂无内容'}</p>}{detailed && <div className="todo-outline-slide-meta">{slide.slide_type && <Tag>{text(slide.slide_type)}</Tag>}{slide.content_points?.length > 0 && <span className="subtle">{slide.content_points.length} 个要点</span>}</div>}</Card>)}</div> },
          { key: 'json', label: 'JSON', children: <pre className="todo-outline-json" tabIndex={0}>{JSON.stringify(outline, null, 2)}</pre> },
        ]} />
      </>}
      {!outline && !state.loading && !state.error && <Empty description="尚未生成大纲" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
      {state.canStart && <div className="todo-outline-next"><span className="subtle">检查大纲后，选择模板与设计方式。</span><Button type="primary" disabled={disabled} onClick={startPpt}>开始生成 PPT</Button></div>}
    </Card>
    <Modal className="todo-outline-dialog" title={view == null ? '' : `第 ${view + 1} 页详情`} open={view != null} modalRender={modalFocus} onCancel={() => setView(null)} footer={<Button onClick={() => setView(null)}>关闭</Button>} destroyOnHidden>{view != null && slides[view] && <><h3>{text(slides[view].title)}</h3><p className="subtle">{text(slides[view].subtitle)}</p>{points(slides[view])}</>}</Modal>
    <Modal title={edit === 'json' ? '编辑 PPT 大纲' : `编辑第 ${Number(edit) + 1} 页`} width={760} className="todo-outline-dialog todo-outline-editor" closable={{ disabled: pending || optimizing }} open={edit != null} modalRender={modalFocus} onCancel={() => { if (!pending && !optimizing) setEdit(null); }} destroyOnHidden footer={<div className="outline-editor-footer"><Button ref={aiTrigger} disabled={pending || optimizing} icon={<RobotOutlined aria-hidden />} onClick={openOptimize}>AI 优化</Button><Space><Button disabled={pending || optimizing} onClick={() => setEdit(null)}>取消</Button><Button type="primary" loading={pending} disabled={optimizing} onClick={save}>保存修改</Button></Space></div>}>
      {editorError && <Alert showIcon type="error" title={editorError} className="page-error" />}
      {edit === 'json' ? <Input.TextArea aria-label="大纲 JSON" className="outline-json-editor" value={json} onChange={event => setJson(event.target.value)} rows={14} disabled={pending || optimizing} /> : <Form form={slideForm} layout="vertical" disabled={pending || optimizing}>
        <Form.Item name="title" label="页面标题" rules={[{ required: true, whitespace: true, message: '请输入页面标题' }]}><Input aria-label="页面标题" /></Form.Item>
        <Form.Item name="subtitle" label="副标题"><Input aria-label="副标题" /></Form.Item>
        <Form.Item name="slide_type" label="幻灯片类型"><Select aria-label="幻灯片类型" virtual={false} options={typeOptions.map(([value, label]) => ({ value, label }))} /></Form.Item>
        <Form.List name="content_points">{(fields, { add, remove }) => <div className="outline-points"><label>内容要点</label>{fields.map((field, index) => <div className="outline-point" key={field.key}><Form.Item {...field} noStyle><Input aria-label={`要点 ${index + 1}`} /></Form.Item><Button danger type="text" aria-label={`删除要点 ${index + 1}`} icon={<DeleteOutlined aria-hidden />} onClick={() => remove(field.name)} /></div>)}<Button icon={<PlusOutlined aria-hidden />} onClick={() => add('')}>添加要点</Button></div>}</Form.List>
        <Form.Item name="description" label="页面描述"><Input.TextArea aria-label="页面描述" rows={3} /></Form.Item>
      </Form>}
    </Modal>
    <Modal className="todo-outline-dialog" title="AI 优化" closable={{ disabled: optimizing }} cancelButtonProps={{ disabled: optimizing }} open={optimizeOpen} modalRender={modalFocus} onCancel={() => { if (!optimizing) setOptimizeOpen(false); }} onOk={optimize} confirmLoading={optimizing} okText="开始优化" cancelText="取消" afterClose={() => aiTrigger.current?.focus()}>
      <p className="subtle">结果会填入编辑窗口，检查后点击“保存修改”。</p>{optimizeError && <Alert type="error" showIcon title={optimizeError} className="page-error" />}<Form form={optimizeForm} layout="vertical" disabled={optimizing}><Form.Item name="requirements" label="优化要求" rules={[{ required: true, whitespace: true, message: '请输入优化要求' }]}><Input.TextArea aria-label="优化要求" rows={4} placeholder="例如：简化内容，突出核心要点" /></Form.Item></Form>
    </Modal>
    <Modal className="todo-outline-dialog" title="重新生成大纲" open={regenerateOpen} modalRender={modalFocus} onCancel={() => setRegenerateOpen(false)} onOk={regenerate} okText="重新生成" cancelText="取消"><p className="subtle">重新生成将替换现有大纲。可补充要求，也可留空沿用原需求。</p><Input.TextArea aria-label="额外要求" rows={4} value={requirements} onChange={event => setRequirements(event.target.value)} /></Modal>
  </section>;
}
