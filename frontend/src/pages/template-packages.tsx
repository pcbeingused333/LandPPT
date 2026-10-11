import { useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Card, Checkbox, Empty, Form, Input, InputNumber, Modal, Pagination, Progress, Select, Space, Spin, Tag, Upload } from 'antd';
import { PlusOutlined, ReloadOutlined, UploadOutlined } from '@ant-design/icons';
import { request, errorText, type ApiData } from '../api';
import { useAdminActions } from '../components/admin-data';
import { modalFocus } from '../components/modal-focus';
import { downloadTemplate, families, packageAPI, packageStatuses, packageWorkspace, postStream, TemplateFrame, TemplateMore, TemplatePreview, templateAPI, useTemplateModalFocus } from '../components/templates';

export default function TemplatePackages({ preferred = 0, selecting = false, busy = false, onSelect }: { preferred?: number; selecting?: boolean; busy?: boolean; onSelect?: (pkg: ApiData, options: ApiData) => Promise<void> }) {
  const [packages, setPackages] = useState<ApiData[]>([]); const [loading, setLoading] = useState(true); const [error, setError] = useState('');
  const [filter, setFilter] = useState('all'); const [page, setPage] = useState(1); const [size, setSize] = useState(6);
  const [allowImages, setAllowImages] = useState(true); const [budget, setBudget] = useState(6);
  const [preview, setPreview] = useState<ApiData>(); const [editing, setEditing] = useState<{ pkg: ApiData; field: 'name' | 'description' }>();
  const [creating, setCreating] = useState(false); const [working, setWorking] = useState(false); const [form] = Form.useForm();
  const read = useRef<AbortController | null>(null); const lock = useRef(false); const actions = useAdminActions(); const { message } = App.useApp();
  async function load() {
    read.current?.abort(); const controller = new AbortController(); read.current = controller; setLoading(true); setError('');
    try { const data = await request(packageAPI, 'GET', undefined, controller.signal); if (!controller.signal.aborted) setPackages(data.packages || []); }
    catch (reason) { if (!controller.signal.aborted) setError((reason as Error).message); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  }
  useEffect(() => { load(); return () => read.current?.abort(); }, []);
  const visible = packages.filter(pkg => filter === 'all' || pkg.status === filter).sort((a, b) => Number(b.id === preferred) - Number(a.id === preferred));
  const current = Math.min(page, Math.max(1, Math.ceil(visible.length / size))); const disabled = busy || working || actions.pending;
  async function perform(task: () => Promise<void>) {
    if (lock.current) return; lock.current = true; setWorking(true); setError('');
    try { await task(); } catch (reason) { setError((reason as Error).message); } finally { lock.current = false; setWorking(false); }
  }
  async function mutate(url: string, method: string, payload?: ApiData) { await actions.run(url, method, payload); await load(); }
  async function workspace(pkg: ApiData) { const bridge = await packageWorkspace(); bridge.PackageWorkspace.open(pkg, { packages, onChange: load }); }
  function edit(pkg: ApiData, field: 'name' | 'description') { form.setFieldsValue({ value: field === 'name' ? pkg.template_name : pkg.description ?? pkg.manifest.description }); setEditing({ pkg, field }); }
  function remove(pkg: ApiData, whole: boolean) {
    const versions = packages.filter(item => item.template_id === pkg.template_id).length;
    actions.confirm(whole ? '删除模板包' : '删除草稿', whole ? `将删除“${pkg.template_name}”及全部 ${versions} 个版本。正在使用它的项目仍可继续编辑和导出，但以后无法选择该模板包。` : `删除“${pkg.template_name}”的草稿 v${pkg.version}？此操作不可撤销。`, async () => {
      const data = await actions.run(whole ? `${templateAPI}/package-templates/${pkg.template_id}` : `${packageAPI}/${pkg.id}`, 'DELETE');
      await load(); message.success(data.hidden ? `已删除，${data.projects} 个项目仍可使用旧版本。` : whole ? '模板包已删除' : '草稿已删除');
    }, true);
  }
  async function importFile(file: File) {
    await perform(async () => {
      if (file.name.toLowerCase().endsWith('.zip')) {
        if (file.size > 65 * 1024 * 1024) throw new Error('模板包 ZIP 不能超过 65 MB');
        const payload = new FormData(); payload.append('file', file);
        const response = await fetch(`${templateAPI}/packages-import`, { method: 'POST', credentials: 'same-origin', body: payload });
        const result = await response.json(); if (!response.ok) throw new Error(errorText(result.detail || '导入失败'));
      } else {
        if (!file.name.toLowerCase().endsWith('.json')) throw new Error('请选择 JSON 或 ZIP 模板包');
        if (file.size > 5 * 1024 * 1024) throw new Error('JSON 文件不能超过 5 MB；含底图的模板包请使用 ZIP');
        await actions.run(packageAPI, 'POST', { manifest: JSON.parse(await file.text()) });
      }
      await load(); message.success('导入草稿成功，请预览后发布。');
    });
  }
  return <section className="template-package-catalogue" aria-label="模板包列表">
    <div className="template-toolbar">
      <Select aria-label="模板包状态" value={filter} onChange={value => { setFilter(value); setPage(1); }} options={[{ value: 'all', label: '全部版本' }, ...Object.entries(packageStatuses).map(([value, label]) => ({ value, label }))]} />
      <Button aria-label="刷新模板包" icon={<ReloadOutlined aria-hidden />} disabled={loading || disabled} onClick={load}>刷新</Button>
      <Space wrap className="template-toolbar-actions">
        <Button disabled={disabled} onClick={() => perform(async () => { const bridge = await packageWorkspace(); bridge.PackagePptxImport.open({ onComplete: async (pkg: ApiData) => { await load(); await workspace(pkg); } }); })}>从 PPTX 创建</Button>
        <Upload accept=".json,.zip" showUploadList={false} beforeUpload={file => { importFile(file); return false; }} disabled={disabled}><Button disabled={disabled} icon={<UploadOutlined aria-hidden />}>导入模板包</Button></Upload>
        <Button disabled={disabled} onClick={() => perform(async () => { await mutate(packageAPI + '/builtin', 'POST'); message.success('内置模板包已添加'); })}>添加内置模板包</Button>
        <Button type="primary" disabled={disabled} icon={<PlusOutlined aria-hidden />} onClick={() => setCreating(true)}>AI 创建模板包</Button>
      </Space>
    </div>
    {selecting && <div className="template-package-options"><Checkbox checked={allowImages} onChange={event => setAllowImages(event.target.checked)} disabled={disabled}>自动配图</Checkbox><label htmlFor="package-image-budget">图片预算</label><InputNumber id="package-image-budget" aria-label="图片预算" min={0} max={40} precision={0} value={budget} onChange={value => setBudget(value ?? 0)} disabled={disabled} /><span className="subtle">仅已发布版本可用于生成</span></div>}
    {error && <Alert className="page-error" type="error" title={error} action={<Button onClick={load} disabled={disabled}>重新加载</Button>} />}
    {actions.error && <Alert className="page-error" type="error" title={actions.error} />}
    {loading && <p role="status"><Spin size="small" /> 正在加载模板包…</p>}
    {!loading && !visible.length && <Empty description={packages.length ? '没有符合条件的模板包版本' : '还没有模板包，可添加内置包或创建自己的设计'} />}
    <div className="template-grid">{visible.slice((current - 1) * size, current * size).map(pkg => {
      const components: ApiData[] = pkg.manifest.components || [];
      const menu = [
        ...(pkg.user_id ? [{ key: 'name', label: '重命名', onClick: () => edit(pkg, 'name') }, { key: 'description', label: '编辑描述', onClick: () => edit(pkg, 'description') }] : []),
        { key: 'export', label: '导出模板包', onClick: () => perform(async () => { const response = await fetch(`${packageAPI}/${pkg.id}/export`, { credentials: 'same-origin' }); if (!response.ok) throw new Error('模板包导出失败'); downloadTemplate(await response.blob(), `${pkg.manifest.package_id}-v${pkg.version}.${response.headers.get('Content-Type')?.includes('zip') ? 'zip' : 'json'}`); }) },
        { key: 'copy', label: '复制为新模板包', onClick: () => perform(async () => { await mutate(packageAPI, 'POST', { manifest: { ...pkg.manifest, name: pkg.template_name, description: pkg.description ?? pkg.manifest.description } }); message.success('已复制为新的模板包草稿'); }) },
        ...(pkg.user_id && pkg.status === 'published' ? [{ key: 'retire', label: '停用此版本', onClick: () => actions.confirm('停用此版本', '引用此版本的项目仍可继续使用。停用后不能再选择它。', () => mutate(`${packageAPI}/${pkg.id}/retire`, 'POST')) }] : []),
        ...(pkg.editable ? [{ key: 'draft-delete', label: '删除此草稿', danger: true, onClick: () => remove(pkg, false) }] : []),
        ...(pkg.user_id ? [{ key: 'delete', label: '删除模板包', danger: true, onClick: () => remove(pkg, true) }] : []),
      ];
      return <Card size="small" className="template-card" key={pkg.id} data-package-id={pkg.id} cover={components[0] ? <TemplateFrame title={pkg.template_name + '预览'} src={`${packageAPI}/${pkg.id}/preview/${encodeURIComponent(components[0].id)}?h=${(pkg.content_hash || '').slice(0, 12)}`} /> : <div className="template-preview-fallback">暂无版式</div>}>
        <div className="template-card-title"><h2>{pkg.template_name}</h2><Tag>{packageStatuses[pkg.status] || pkg.status}</Tag></div>
        <p className="subtle">v{pkg.version} · {components.length} 个页面{pkg.id === preferred ? ' · 需求中已选' : ''}</p>
        <p className="template-description">{pkg.description ?? pkg.manifest.description ?? '暂无描述'}</p>
        <Space wrap className="template-card-tags">{Array.from(new Set(components.map(item => item.family))).map(family => <Tag key={family}>{families[family] || family}</Tag>)}</Space>
        <div className="template-card-actions">
          {selecting && <Button type="primary" disabled={pkg.status !== 'published' || disabled} onClick={() => onSelect?.(pkg, { allow_images: allowImages, image_budget: budget })}>使用此包生成</Button>}
          {pkg.editable && <Button disabled={disabled} onClick={() => actions.confirm('校验并发布', '发布后此版本保持固定，后续编辑会创建草稿。', () => mutate(`${packageAPI}/${pkg.id}/publish`, 'POST'))}>校验并发布</Button>}
          <div className="template-card-action-row"><Button disabled={disabled} onClick={() => perform(() => workspace(pkg))}>{pkg.editable ? '编辑草稿' : '编辑'}</Button><Button onClick={() => setPreview(pkg)} disabled={disabled}>预览</Button><TemplateMore name={pkg.template_name} items={menu} disabled={disabled} /></div>
        </div>
      </Card>;
    })}</div>
    <div className="projects-pagination"><span className="subtle">共 {visible.length} 个版本</span><Pagination current={current} total={visible.length} pageSize={size} pageSizeOptions={[6, 12, 24]} showSizeChanger showLessItems onChange={(next, pageSize) => { setPage(pageSize === size ? next : 1); setSize(pageSize); }} /></div>
    <p className="template-settings-link subtle">快速模式自动匹配每页版式。<a href="/ai-config#jev-config">配置匹配模型</a></p>
    {preview && <TemplatePreview key={preview.id} template={preview} onClose={() => setPreview(undefined)} />}
    <Modal open={!!editing} centered title={editing?.field === 'name' ? '重命名模板包' : '编辑模板包描述'} okText="保存" cancelText="取消" confirmLoading={actions.pending} cancelButtonProps={{ disabled: actions.pending }} closable={!actions.pending} keyboard={!actions.pending} mask={{ closable: !actions.pending }} onCancel={() => setEditing(undefined)} onOk={() => form.submit()} modalRender={modalFocus}>
      <Form form={form} layout="vertical" disabled={actions.pending} onFinish={async values => { if (!editing) return; try { await actions.run(`${templateAPI}/package-templates/${editing.pkg.template_id}`, 'PATCH', { [editing.field]: values.value?.trim() || '' }); setEditing(undefined); await load(); message.success('已保存'); } catch { /* Keep the entered value for retry. */ } }}>
        {actions.error && <Alert type="error" title={actions.error} />}
        <Form.Item name="value" label={editing?.field === 'name' ? '名称' : '描述'} rules={editing?.field === 'name' ? [{ required: true, whitespace: true, message: '请输入名称' }] : []}>{editing?.field === 'name' ? <Input aria-label="模板包名称" maxLength={255} /> : <Input.TextArea aria-label="模板包描述" rows={5} maxLength={2000} showCount />}</Form.Item>
      </Form>
    </Modal>
    {creating && <PackageGeneration onClose={() => setCreating(false)} onComplete={load} />}
  </section>;
}

function PackageGeneration({ onClose, onComplete }: { onClose: () => void; onComplete: () => Promise<void> }) {
  useTemplateModalFocus();
  const [form] = Form.useForm(); const [pending, setPending] = useState(false); const [status, setStatus] = useState('生成完成后会保存为草稿，请预览后发布。'); const [progress, setProgress] = useState<number>(); const [error, setError] = useState(''); const [done, setDone] = useState(false);
  const controller = useRef<AbortController | null>(null); const lock = useRef(false);
  useEffect(() => () => controller.current?.abort(), []);
  return <Modal open centered title="AI 创建模板包" footer={<Space wrap><Button onClick={onClose} disabled={pending}>关闭</Button>{pending && <Button onClick={() => controller.current?.abort()}>停止接收</Button>}{!done && <Button type="primary" loading={pending} aria-label="开始设计" onClick={() => form.submit()}>开始设计</Button>}</Space>} closable={!pending} keyboard={!pending} mask={{ closable: !pending }} onCancel={onClose} modalRender={modalFocus}>
    <Form form={form} layout="vertical" disabled={pending || done} onFinish={async values => {
      if (lock.current) return; lock.current = true; setPending(true); setProgress(undefined); setError(''); setStatus('正在规划主题…'); controller.current = new AbortController();
      try {
        const data = await postStream(`${templateAPI}/packages-generate`, { prompt: values.prompt }, controller.current.signal, item => { if (item.message) setStatus(item.message); if (item.total) setProgress(Math.min(99, Math.round(item.current / item.total * 100))); });
        setDone(true); setProgress(100); setStatus(data.partial ? '部分版式未通过校验，可用部分已保存为草稿。请预览后决定是否发布。' : '草稿已保存，请预览后发布。'); await onComplete();
      } catch (reason) { setError((reason as Error).name === 'AbortError' ? '已停止接收。请检查草稿列表后再重试，服务器可能仍在处理。' : (reason as Error).message); } finally { lock.current = false; setPending(false); }
    }}><Form.Item name="prompt" label="设计要求" rules={[{ required: true, whitespace: true, message: '请描述希望的风格与用途' }]}><Input.TextArea aria-label="模板包设计要求" rows={5} placeholder="描述用途、配色、字体和需要的页面类型" /></Form.Item></Form>
    {pending && <Spin size="small" />}{progress != null && <Progress percent={progress} status={error ? 'exception' : done ? 'success' : 'active'} size="small" />}
    <p role="status">{status}</p>{error && <Alert type="error" title={error} />}
  </Modal>;
}
