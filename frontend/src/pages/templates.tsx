import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Card, Empty, Form, Input, Modal, Pagination, Select, Space, Spin, Tabs, Tag, Upload } from 'antd';
import { CheckOutlined, PlusOutlined, ReloadOutlined, UploadOutlined } from '@ant-design/icons';
import { request, type ApiData } from '../api';
import { useAdminActions } from '../components/admin-data';
import { modalFocus } from '../components/modal-focus';
import { downloadTemplate, templateAPI, TemplateMore, TemplatePreview, TemplateThumbnail } from '../components/templates';
import { TemplateEdit, TemplateGeneration } from './template-edit';

const TemplatePackages = lazy(() => import('./template-packages'));

function useTemplateList(selecting: boolean) {
  const [rows, setRows] = useState<ApiData[]>([]); const [total, setTotal] = useState(0); const [page, setPage] = useState(1); const [size, setSize] = useState(selecting ? 9 : 6); const [search, setSearch] = useState(''); const [query, setQuery] = useState(''); const [tag, setTag] = useState(''); const [tags, setTags] = useState<string[]>([]);
  const [loading, setLoading] = useState(true); const [error, setError] = useState(''); const [defaultId, setDefaultId] = useState<number>();
  const read = useRef<AbortController | null>(null); const latest = useRef({ page: 1, page_size: size, search: '', tags: '' });
  async function load(target = latest.current) {
    read.current?.abort(); const controller = new AbortController(); read.current = controller; latest.current = target; setLoading(true); setError('');
    const params = new URLSearchParams({ active_only: 'true', page: String(target.page), page_size: String(target.page_size), ...(target.search ? { search: target.search } : {}), ...(target.tags ? { tags: target.tags } : {}) });
    try {
      const data = await request(templateAPI + '/?' + params, 'GET', undefined, controller.signal);
      if (controller.signal.aborted) return;
      const count = data.pagination ? Number(data.pagination.total_count || 0) : Array.isArray(data) ? data.length : 0; const last = Math.max(1, Math.ceil(count / target.page_size));
      if (target.page > last) { await load({ ...target, page: last }); return; }
      setRows(Array.isArray(data) ? data : data.templates || []); setTotal(count); setPage(Number(data.pagination?.current_page || target.page));
    } catch (reason) { if (!controller.signal.aborted) setError((reason as Error).message); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  }
  useEffect(() => { const timer = setTimeout(() => setQuery(search.trim()), 300); return () => clearTimeout(timer); }, [search]);
  useEffect(() => { load({ page: 1, page_size: size, search: query, tags: tag }); return () => read.current?.abort(); }, [size, query, tag]);
  useEffect(() => {
    const controller = new AbortController();
    request(templateAPI + '/default/template', 'GET', undefined, controller.signal).then(data => { if (!controller.signal.aborted) setDefaultId(Number(data.id) || undefined); }).catch(() => {});
    (async () => {
      const catalogue = new Set<string>(); let next = 1; let pages = 1;
      do { const data = await request(`${templateAPI}/?active_only=true&page=${next}&page_size=100`, 'GET', undefined, controller.signal); for (const row of data.templates || []) for (const item of row.tags || []) if (typeof item === 'string' && item.trim()) catalogue.add(item.trim()); pages = data.pagination?.total_pages || 1; next++; } while (next <= pages && !controller.signal.aborted);
      if (!controller.signal.aborted) setTags(Array.from(catalogue).sort());
    })().catch(() => {});
    return () => controller.abort();
  }, []);
  return { rows, total, page, size, setSize, search, setSearch, tag, setTag, tags, loading, error, defaultId, setDefaultId, refresh: load, changePage: (page: number) => load({ ...latest.current, page }) };
}

export default function Templates({ data }: { data: ApiData }) {
  const selecting = data.page === 'template-selection';
  function requested() {
    const params = new URLSearchParams(location.search);
    if (!selecting) return params.get('tab') === 'packages' ? 'packages' : 'regular';
    const mode = params.get('mode');
    return mode === 'package' || (mode !== 'freeform' && data.packagePreference?.mode === 'package') ? 'packages' : 'regular';
  }
  const [tab, setTab] = useState(requested); const [selected, setSelected] = useState<ApiData>(); const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const locked = useRef(false);
  useEffect(() => { const restore = () => setTab(requested()); window.addEventListener('popstate', restore); return () => window.removeEventListener('popstate', restore); }, []);
  function changeTab(key: string) { setTab(key); const url = new URL(location.href); url.searchParams.set(selecting ? 'mode' : 'tab', selecting ? key === 'packages' ? 'package' : 'freeform' : key); history.replaceState(null, '', url); }
  async function start(template?: ApiData, pkg?: ApiData, options?: ApiData) {
    if (locked.current) return; locked.current = true; setBusy(true); setError('');
    try {
      if (!data.projectId) throw new Error('无法获取项目 ID，请从项目列表重新进入。');
      const project = encodeURIComponent(data.projectId);
      await request(`/api/projects/${project}/${pkg ? 'template-package' : 'select-template'}`, 'POST', pkg ? { version_id: pkg.id, options } : { project_id: data.projectId, selected_template_id: template?.id ?? null, template_mode: template?.free ? 'free' : template ? 'global' : 'default' });
      location.href = `/projects/${project}/todo-editor?auto_start=true`;
    } catch (reason) { setError((reason as Error).message); locked.current = false; setBusy(false); }
  }
  return <div className="templates-page">
    <div className="page-heading"><div><h1>{selecting ? '选择 PPT 模板' : '模板管理'}</h1><p>{selecting ? data.projectTopic || '为演示文稿选择生成方式与模板' : '管理逐页设计的母版与快速生成的模板包'}</p></div><Button href={selecting ? `/projects/${encodeURIComponent(data.projectId || '')}` : 'https://landppt-template.52yyds.top/'} target={selecting ? undefined : '_blank'} rel={selecting ? undefined : 'noopener noreferrer'}>{selecting ? '返回项目' : '模板广场'}</Button></div>
    {data.packageNotice && <Alert type="warning" title={data.packageNotice} className="page-error" />}
    {error && <Alert type="error" title={error} className="page-error" />}
    <Tabs activeKey={tab} onChange={changeTab} size="small" items={[
      { key: 'regular', label: selecting ? '自由设计' : '普通模板', disabled: busy, children: <RegularTemplates selecting={selecting} isAdmin={!!data.user?.is_admin} busy={busy} selected={selected} onSelect={setSelected} onStart={start} /> },
      { key: 'packages', label: selecting ? '快速模式 · 模板包' : '模板包', disabled: busy, children: <Suspense fallback={<p role="status"><Spin size="small" /> 正在加载模板包…</p>}><TemplatePackages selecting={selecting} preferred={Number(data.packagePreference?.version_id || 0)} busy={busy} onSelect={(pkg, options) => start(undefined, pkg, options)} /></Suspense> },
    ]} />
    {selecting && tab === 'regular' && <div className="template-selection-bar"><div aria-live="polite"><strong>{selected ? selected.template_name : '尚未选择模板'}</strong><span className="subtle">{selected ? '确认后开始生成' : '选择母版，或使用当前默认模板'}</span></div><Space wrap><Button disabled={busy} onClick={() => start()}>使用默认模板</Button><Button type="primary" aria-label="开始生成 PPT" loading={busy} disabled={!selected} onClick={() => start(selected)}>开始生成</Button></Space></div>}
  </div>;
}

function RegularTemplates({ selecting, isAdmin, busy, selected, onSelect, onStart }: { selecting: boolean; isAdmin: boolean; busy: boolean; selected?: ApiData; onSelect: (template: ApiData) => void; onStart: (template?: ApiData) => Promise<void> }) {
  const state = useTemplateList(selecting); const actions = useAdminActions(); const { message } = App.useApp(); const [editing, setEditing] = useState<number | null>(); const [generating, setGenerating] = useState(false); const [preview, setPreview] = useState<ApiData>(); const [copy, setCopy] = useState<ApiData>(); const [form] = Form.useForm(); const [working, setWorking] = useState(false); const [error, setError] = useState(''); const lock = useRef(false);
  const disabled = busy || working || actions.pending;
  async function perform(task: () => Promise<void>) { if (lock.current) return; lock.current = true; setWorking(true); setError(''); try { await task(); } catch (reason) { setError((reason as Error).message); } finally { lock.current = false; setWorking(false); } }
  async function changed(url: string, method: string, body?: ApiData) { await actions.run(url, method, body); await state.refresh(); }
  const free = { free: true, template_name: '自由模板 · AI 设计', description: 'AI 根据大纲设计专属风格、配色与版式' };
  async function importFile(file: File) {
    await perform(async () => {
      const content = await file.text(); const lower = file.name.toLowerCase();
      const payload = lower.endsWith('.json') ? JSON.parse(content) : lower.endsWith('.html') ? { template_name: file.name.slice(0, -5), description: `从文件 ${file.name} 导入`, html_template: content, tags: ['导入'], is_default: false } : null;
      if (!payload?.template_name || !payload.html_template) throw new Error('文件缺少模板名称或 HTML 内容');
      payload.tags = typeof payload.tags === 'string' ? payload.tags.split(',').map((value: string) => value.trim()).filter(Boolean) : Array.isArray(payload.tags) ? payload.tags : [];
      await changed(templateAPI + '/', 'POST', payload); message.success('模板导入成功');
    });
  }
  async function exportPPTX(template: ApiData) {
    const url = '/static/js/pages/template/global_master/globalMasterTemplates.exportHelpers.js?v=20261011'; const helpers = await import(/* @vite-ignore */ url);
    const exporter = await helpers.ensureDomToPptxReady(); const detail = await request(`${templateAPI}/${template.id}`);
    if (!detail.html_template) throw new Error('模板内容为空，无法导出');
    const host = document.createElement('div'); host.style.cssText = 'position:fixed;left:-99999px;top:-99999px;width:1px;height:1px;overflow:hidden;opacity:0;pointer-events:none'; document.body.append(host);
    const elements = (async function* () {
      const iframe = document.createElement('iframe'); iframe.style.cssText = 'width:1280px;height:720px;border:none'; iframe.setAttribute('aria-hidden', 'true'); host.append(iframe);
      try { const sample = { kind: 'template', pageTitle: '', mainHeading: '', subtitle: '', pageContent: '', notes: '' }; await helpers.loadHtmlIntoIframe(iframe, helpers.renderTemplateSampleHtml(detail.html_template, sample, 1, 1)); await helpers.waitForIframeVisualReady(iframe); if (!iframe.contentDocument?.body) throw new Error('模板渲染失败'); yield iframe.contentDocument.body; } finally { iframe.remove(); }
    })();
    try { await exporter.exportToPptx(elements, { fileName: `${helpers.sanitizeFileName(detail.template_name || '模板')}_PPTX模板.pptx`, autoEmbedFonts: true, svgAsVector: false, slideNotes: [] }); message.success('PPTX 模板导出完成'); } finally { host.remove(); }
  }
  return <section aria-label={selecting ? '选择普通模板' : '普通模板列表'}>
    <div className="template-toolbar"><Input.Search className="template-search" aria-label="搜索模板" value={state.search} onChange={event => state.setSearch(event.target.value)} placeholder="搜索名称或描述" allowClear /><Select aria-label="模板标签" value={state.tag} onChange={state.setTag} options={[{ value: '', label: '全部标签' }, ...state.tags.map(tag => ({ value: tag, label: tag }))]} /><Button aria-label="刷新普通模板" icon={<ReloadOutlined aria-hidden />} disabled={state.loading || disabled} onClick={() => state.refresh()}>刷新</Button>
      {!selecting && <Space wrap className="template-toolbar-actions"><Upload accept=".json,.html" showUploadList={false} beforeUpload={file => { importFile(file); return false; }} disabled={disabled}><Button disabled={disabled} icon={<UploadOutlined aria-hidden />}>导入模板</Button></Upload><Button disabled={disabled} onClick={() => setGenerating(true)}>AI 生成模板</Button><Button id="createTemplateBtn" type="primary" icon={<PlusOutlined aria-hidden />} disabled={disabled} onClick={() => setEditing(null)}>新建模板</Button></Space>}
    </div>
    {(state.error || error || actions.error) && <Alert type="error" className="page-error" title={state.error || error || actions.error} action={state.error ? <Button onClick={() => state.refresh()}>重试</Button> : undefined} />}
    {state.loading && <p role="status"><Spin size="small" /> 正在加载模板…</p>}
    <div className="template-grid">
      {selecting && <Card className={`template-card template-free-card${selected?.free ? ' is-selected' : ''}`} size="small"><div className="template-free-preview"><PlusOutlined aria-hidden /><strong>从大纲开始设计</strong><span>专属风格 · AI 自动设计</span></div><h2>{free.template_name}</h2><p className="template-description">{free.description}</p><div className="template-card-actions"><Button aria-pressed={!!selected?.free} disabled={disabled} onClick={() => onSelect(free)}>{selected?.free ? '已选择' : '选择自由模板'}</Button><Button type="primary" disabled={disabled} onClick={() => { onSelect(free); onStart(free); }}>选择并开始</Button></div></Card>}
      {state.rows.map(template => {
        const owned = template.user_id != null; const editable = isAdmin || owned; const defaultTemplate = state.defaultId ? Number(template.id) === state.defaultId : !!template.is_default;
        const menu = [
          { key: 'copy', label: '复制', onClick: () => { form.setFieldsValue({ name: template.template_name + ' 副本' }); setCopy(template); } },
          { key: 'json', label: '导出 JSON', onClick: () => perform(async () => { const data = await request(`${templateAPI}/${template.id}`); downloadTemplate(new Blob([JSON.stringify({ template_name: data.template_name, description: data.description, html_template: data.html_template, tags: data.tags, is_default: false, export_info: { exported_at: new Date().toISOString(), original_id: data.id, original_created_at: data.created_at } }, null, 2)], { type: 'application/json' }), `${data.template_name}_${new Date().toISOString().split('T')[0]}.json`); }) },
          { key: 'pptx', label: '导出 PPTX', onClick: () => perform(() => exportPPTX(template)) },
          ...(editable && !defaultTemplate ? [{ key: 'default', label: '设为默认', onClick: () => actions.confirm('设为默认模板', `将“${template.template_name}”设为默认模板？`, async () => { await changed(`${templateAPI}/${template.id}/set-default`, 'POST'); state.setDefaultId(Number(template.id)); }) }] : []),
          ...(editable && !template.is_default ? [{ key: 'delete', label: '删除', danger: true, onClick: () => actions.confirm('删除模板', `确认删除“${template.template_name}”？此操作不可撤销。`, () => changed(`${templateAPI}/${template.id}`, 'DELETE'), true) }] : []),
        ];
        return <Card key={template.id} size="small" className={`template-card${selected?.id === template.id ? ' is-selected' : ''}`} data-template-id={template.id} cover={<TemplateThumbnail template={template} />}>
          <div className="template-card-title"><h2>{template.template_name}</h2>{defaultTemplate && <Tag icon={<CheckOutlined aria-hidden />}>默认</Tag>}</div>
          <p className="template-description">{template.description || '暂无描述'}</p><Space wrap className="template-card-tags">{(template.tags || []).map((tag: string, index: number) => <Tag key={index}>{tag}</Tag>)}</Space><p className="subtle">使用 {template.usage_count || 0} 次 · {template.created_by || '系统'}</p>
          <div className="template-card-action-row">{selecting ? <><Button aria-pressed={selected?.id === template.id} disabled={disabled} onClick={() => onSelect(template)}>{selected?.id === template.id ? '已选择' : '选择'}</Button><Button type="primary" disabled={disabled} onClick={() => { onSelect(template); onStart(template); }}>选择并开始</Button></> : <Button type="primary" disabled={disabled} onClick={() => editable ? setEditing(Number(template.id)) : setPreview(template)}>{editable ? '编辑' : '预览'}</Button>}
            {(!selecting && editable || selecting) && <Button disabled={disabled} onClick={() => setPreview(template)}>预览</Button>}
            {!selecting && <TemplateMore name={template.template_name} items={menu} disabled={disabled} />}
          </div>
        </Card>;
      })}
    </div>
    {!state.loading && !state.rows.length && <Empty description={state.search || state.tag ? '没有符合条件的模板' : selecting ? '暂无母版，也可以选择自由模板或使用默认模板' : '暂无模板，可新建或导入母版'} />}
    <div className="projects-pagination"><span className="subtle">共 {state.total} 个模板</span><Pagination current={state.page} total={state.total} pageSize={state.size} pageSizeOptions={selecting ? [9, 18, 36] : [6, 12, 24, 48]} showSizeChanger showLessItems disabled={state.loading} onChange={(page, size) => size !== state.size ? state.setSize(size) : state.changePage(page)} /></div>
    {editing !== undefined && <TemplateEdit key={editing ?? 'new'} id={editing ?? undefined} onClose={() => setEditing(undefined)} onSaved={() => state.refresh()} />}
    {generating && <TemplateGeneration onClose={() => setGenerating(false)} onSaved={() => state.refresh()} />}
    {preview && <TemplatePreview key={preview.id} template={preview} onClose={() => setPreview(undefined)} />}
    <Modal open={!!copy} centered title="复制模板" okText="复制" cancelText="取消" confirmLoading={actions.pending} cancelButtonProps={{ disabled: actions.pending }} closable={!actions.pending} keyboard={!actions.pending} mask={{ closable: !actions.pending }} onCancel={() => setCopy(undefined)} onOk={() => form.submit()} modalRender={modalFocus}>
      {actions.error && <Alert type="error" title={actions.error} />}<Form form={form} layout="vertical" disabled={actions.pending} onFinish={async values => { if (!copy) return; try { await changed(`${templateAPI}/${copy.id}/duplicate?new_name=${encodeURIComponent(values.name.trim())}`, 'POST'); setCopy(undefined); message.success('模板已复制'); } catch { /* Retry with the same name. */ } }}><Form.Item name="name" label="新模板名称" rules={[{ required: true, whitespace: true, message: '请输入新模板名称' }]}><Input aria-label="新模板名称" /></Form.Item></Form>
    </Modal>
  </section>;
}
