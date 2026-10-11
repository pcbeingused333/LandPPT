import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Card, Checkbox, Collapse, Empty, Form, Input, InputNumber, Select, Space, Tabs, Upload } from 'antd';
import { ArrowRightOutlined, InboxOutlined, ReloadOutlined } from '@ant-design/icons';
import { errorText, request, type ApiData } from '../api';

const audienceOptions = ['企业管理层', '技术团队', '销售团队', '学生群体', '学术研究者', '投资人', '客户群体', '培训学员', '项目团队', '行业专家', '普通大众', '自定义'];
const choices = (pairs: string[][]) => pairs.map(([value, label]) => ({ value, label }));
const stages = choices([['outline', '生成大纲'], ['template', '选择模板'], ['ppt', '生成 PPT'], ['speech_script', '生成演讲稿'], ['narration_audio', '生成配音'], ['video', '导出讲解视频']]);
const extensions = ['pdf', 'docx', 'txt', 'md', 'jpg', 'jpeg', 'png', 'xlsx', 'csv'];
const defaults = { topic: '', requirements: '', scenario: 'general', audience_type: '普通大众', custom_audience: '', page_count_mode: 'ai_decide', min_pages: 8, max_pages: 15, ppt_style: 'general', custom_style_prompt: '', language: 'zh', render_mode: 'html', generation_mode: 'freeform', package_version_id: '', network_mode: false, include_transition_pages: false, include_page_numbers: true, file_processing_mode: 'markitdown', content_analysis_depth: 'fast', content_urls: '', unattended_mode: false, unattended_template_mode: 'auto', unattended_template_id: '', stop_at_stage: 'ppt', unattended_notify_in_app: true, unattended_notify_email: false };
const urls = (value: string) => String(value || '').split(/[\n,;\t ]+/).map(item => item.trim()).filter(Boolean).slice(0, 50);
function projectURL(value: unknown) {
  if (typeof value !== 'string' || !value) return '';
  try { const url = new URL(value, location.origin); return url.origin === location.origin && url.pathname.startsWith('/projects/') ? url.pathname + url.search + url.hash : ''; } catch { return ''; }
}

export default function CreateProject({ data }: { data: ApiData }) {
  const [form] = Form.useForm();
  const initial = { ...defaults, scenario: data.selectedScenario || 'general', ...data.createDefaults, unattended_template_id: String(data.templateOptions?.[0]?.id || '') };
  const watched = Form.useWatch(values => values, form);
  const values = { ...initial, ...watched };
  const [sourceTab, setSourceTab] = useState('manual'); const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState(''); const [warning, setWarning] = useState(''); const [redirect, setRedirect] = useState('');
  const [pending, setPending] = useState(false); const locked = useRef(false);
  const [packages, setPackages] = useState<ApiData[]>([]); const [packageError, setPackageError] = useState(''); const [packageLoading, setPackageLoading] = useState(false); const [refresh, setRefresh] = useState(0);
  const fast = values.generation_mode === 'package'; const links = urls(values.content_urls);
  const source = files.length ? 'file' : links.length ? 'url' : 'manual';
  useEffect(() => {
    if (!fast) return;
    const controller = new AbortController(); setPackageLoading(true); setPackageError('');
    request('/api/global-master-templates/packages', 'GET', undefined, controller.signal).then(result => {
      if (controller.signal.aborted) return;
      if (!Array.isArray(result.packages)) throw new Error('模板包列表无效，请重试');
      const published = result.packages.filter(item => item.status === 'published'); setPackages(published);
      const current = form.getFieldValue('package_version_id');
      if (current && !published.some(item => String(item.id) === current)) form.setFieldValue('package_version_id', '');
    }).catch(reason => { if (!controller.signal.aborted) setPackageError(reason.message); })
      .finally(() => { if (!controller.signal.aborted) setPackageLoading(false); });
    return () => controller.abort();
  }, [fast, refresh, form]);
  function addFile(file: File) {
    if (!extensions.includes(file.name.split('.').pop()?.toLowerCase() || '')) setWarning(`不支持的文件类型：${file.name}`);
    else if (file.size > 100 * 1024 * 1024) setWarning(`文件超过 100MB：${file.name}`);
    else setFiles(current => current.some(item => item.name === file.name && item.size === file.size) ? current : [...current, file]);
    return false;
  }
  async function submit(submitted: ApiData) {
    if (locked.current) return;
    const input = { ...initial, ...form.getFieldsValue(true), ...submitted };
    setError(''); setRedirect('');
    if (fast && (packageLoading || packageError || !packages.some(item => String(item.id) === input.package_version_id))) { setError('快速模式需要先选择一个已发布的模板包。'); form.scrollToField('package_version_id', { focus: true }); return; }
    let min = Math.min(50, Math.max(5, Math.trunc(Number(input.min_pages) || 8)));
    let max = Math.min(50, Math.max(5, Math.trunc(Number(input.max_pages) || 15)));
    if (min > max) [min, max] = [max, min];
    form.setFieldsValue({ min_pages: min, max_pages: max });
    Object.assign(input, { min_pages: min, max_pages: max, content_source: source, render_mode: fast ? 'svg' : input.render_mode, package_version_id: fast ? input.package_version_id : '0', unattended_mode: !!data.user?.is_admin && !!input.unattended_mode, unattended_template_id: input.unattended_template_mode === 'global' ? input.unattended_template_id : '' });
    const body = new FormData();
    for (const key of Object.keys(defaults).filter(key => key !== 'content_urls')) {
      const value = input[key]; body.append(key, typeof value === 'boolean' ? String(value) : String(value ?? '').trim());
    }
    body.append('content_source', source);
    if (source === 'url') body.append('content_urls', links.join('\n'));
    if (source === 'file') files.forEach(file => body.append('file_upload', file));
    locked.current = true; setPending(true); let navigating = false;
    try {
      const response = await fetch('/projects/create-and-confirm', { method: 'POST', credentials: 'same-origin', headers: { Accept: 'application/json' }, body });
      const result = await response.json().catch(() => ({})); const target = projectURL(result.redirect_url);
      if (response.ok && result.status === 'success' && target) { navigating = true; location.assign(target); return; }
      setRedirect(target);
      throw new Error(errorText(result.detail || result.message || `创建失败（HTTP ${response.status}）`));
    } catch (reason) { setError((reason as Error).message); }
    finally { if (!navigating) { locked.current = false; setPending(false); } }
  }
  const select = (name: string, label: string, options: { value: string; label: string }[], disabled = false) => <Form.Item name={name} label={label}><Select aria-label={label} options={options} disabled={pending || disabled} /></Form.Item>;
  const check = (name: string, label: string) => <Form.Item name={name} valuePropName="checked" className="create-checkbox"><Checkbox>{label}</Checkbox></Form.Item>;
  const parsing = <div className="create-field-grid">
    {select('file_processing_mode', 'PDF 处理方式', choices([['markitdown', '标准处理 · MarkItDown'], ['magic_pdf', '高质量 · Mineru（提取图片）']]))}
    {select('content_analysis_depth', '解析深度', choices([['fast', '快速解析'], ['standard', '标准解析'], ['deep', '深度解析']]))}
  </div>;
  return <div className="create-project-page">
    <div className="page-heading"><div><h1>创建 PPT</h1><p>填写主题与资料，设定生成方式。</p></div><Button href="/projects">项目列表</Button></div>
    <Form name="create" form={form} layout="vertical" initialValues={initial} disabled={pending} scrollToFirstError={{ focus: true }} onFinish={submit}
      onValuesChange={changed => { if (changed.generation_mode === 'package') form.setFieldValue('render_mode', 'svg'); }}
      onKeyDown={event => { if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { event.preventDefault(); if (!locked.current) form.submit(); } }}
      onFinishFailed={({ errorFields }) => { if (errorFields[0]) form.scrollToField(errorFields[0].name, { focus: true }); }}>
      <div className="create-project-grid">
        <div className="create-main">
          <Card size="small" title="演示内容">
            <Form.Item name="topic" label="PPT 主题" rules={[{ required: true, whitespace: true, message: '请先填写 PPT 主题' }]}>
              <Input aria-label="PPT 主题" placeholder="例如：人工智能技术发展趋势" onPressEnter={event => { if (!event.ctrlKey && !event.metaKey) { event.preventDefault(); form.getFieldInstance('requirements')?.focus(); } }} />
            </Form.Item>
            <Form.Item name="requirements" label="具体需求（选填）"><Input.TextArea aria-label="具体需求" autoSize={{ minRows: 4, maxRows: 10 }} placeholder="重点内容、章节思路、数据素材、风格偏好…" /></Form.Item>
          </Card>
          <Card size="small" title="参考资料（选填）" extra={<span className="subtle" role="status">{source === 'file' ? `${files.length} 个附件` : source === 'url' ? `${links.length} 个链接` : '未添加资料'}</span>}>
            <Tabs activeKey={sourceTab} onChange={setSourceTab} items={[
              { key: 'manual', label: '主题与需求', children: <p className="subtle">根据上方主题和需求生成内容，也可添加文件或网页链接作为参考。</p> },
              { key: 'file', label: '文件资料', children: <>
                <Upload.Dragger multiple disabled={pending} accept={extensions.map(ext => '.' + ext).join(',')} beforeUpload={addFile} showUploadList={false}>
                  <InboxOutlined aria-hidden className="create-upload-icon" /><p>点击选择或拖入文件</p><p className="subtle">PDF / DOCX / TXT / MD / 图片 / XLSX / CSV，单个最大 100MB</p>
                </Upload.Dragger>
              </> },
              { key: 'url', label: '网页链接', children: <Form.Item name="content_urls" label="内容链接" extra="每行一个或逗号分隔，最多使用前 50 个链接。支持网页与文件 URL。"><Input.TextArea aria-label="内容链接" autoSize={{ minRows: 3, maxRows: 6 }} placeholder="https://example.com/article" /></Form.Item> },
            ]} />
            {sourceTab !== 'manual' && parsing}
            {files.length > 0 && <div className="create-files" aria-label="已选附件">{files.map((file, index) => <div className="create-file" key={file.name + ':' + file.size}><span>{file.name}<small className="subtle">{(file.size / 1024).toFixed(1)} KB</small></span><Button size="small" disabled={pending} aria-label={`移除附件 ${file.name}`} onClick={() => setFiles(current => current.filter((_, i) => i !== index))}>移除</Button></div>)}</div>}
            {files.length > 0 && links.length > 0 && <Alert type="info" title="已同时添加附件和链接，将优先使用附件。移除全部附件后会使用链接。" />}
            {warning && <Alert className="page-error" type="warning" title={warning} closable onClose={() => setWarning('')} />}
          </Card>
          <Card size="small" title="附加设置">
            {check('network_mode', '联网深度研究')}
            <p className="subtle create-research-help">联网研究需先在 <a href="/ai-config">系统配置</a> 填写 Tavily Key / SearXNG 地址。<a href="/research">查看研究状态</a></p>
            <Collapse items={[{ key: 'pages', label: '章节与页码', children: <>{check('include_transition_pages', '章节过渡页')}{check('include_page_numbers', '页码 / Footer')}</> },
              ...(data.user?.is_admin ? [{ key: 'unattended', label: '无人值守', children: <>
                {check('unattended_mode', '开启无人值守')}
                <p className="subtle">自动执行到所选阶段，无需人工确认。</p>
                {select('stop_at_stage', '停止阶段', stages)}
                {select('unattended_template_mode', '无人值守模板', choices([['auto', '使用我的默认模板'], ['global', '指定已有模板'], ['free', '自由模板（AI 按大纲生成）']]))}
                {values.unattended_template_mode === 'global' && <Form.Item name="unattended_template_id" label="选择模板"><Select aria-label="选择模板" placeholder="暂无可用模板" options={(data.templateOptions || []).map((item: ApiData) => ({ value: String(item.id), label: item.name + (item.is_default ? '（默认）' : '') }))} /></Form.Item>}
                {check('unattended_notify_in_app', '系统通知')}{check('unattended_notify_email', '邮件通知')}
              </> }] : [])]} />
          </Card>
        </div>
        <Card size="small" title="生成设置" className="create-settings">
          {select('generation_mode', '生成方式', choices([['freeform', '自由设计'], ['package', '快速模式（模板包）']]))}
          {fast && <div className="create-package-field">
            <Form.Item name="package_version_id" label="已发布模板包"><Select aria-label="已发布模板包" disabled={pending || packageLoading || !!packageError} loading={packageLoading} placeholder="请选择模板包" options={packages.map(item => ({ value: String(item.id), label: `${item.template_name} · v${item.version}` }))} /></Form.Item>
            <Space wrap><Button size="small" icon={<ReloadOutlined aria-hidden />} loading={packageLoading} disabled={pending} onClick={() => setRefresh(value => value + 1)}>刷新模板包</Button><a href="/global-master-templates?tab=packages" target="_blank" rel="noopener">管理模板包</a></Space>
            {packageError ? <Alert className="page-error" type="error" title={packageError} /> : !packageLoading && !packages.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无已发布模板包" /> : <p className="subtle">参考模板包规划大纲，使用 SVG 绘制。</p>}
          </div>}
          <div className="create-field-grid">
            {select('scenario', '场景', (data.scenarios?.length ? data.scenarios : [{ id: 'general', name: '通用' }]).map((item: ApiData) => ({ value: item.id, label: item.name })))}
            {select('audience_type', '目标受众', audienceOptions.map(value => ({ value, label: value })))}
          </div>
          {values.audience_type === '自定义' && <Form.Item name="custom_audience" label="自定义受众描述" rules={[{ required: true, whitespace: true, message: '请描述自定义受众' }]}><Input aria-label="自定义受众描述" placeholder="例如：初级程序员" /></Form.Item>}
          {select('page_count_mode', '页数', choices([['ai_decide', 'AI 智能决定'], ['custom_range', '自定义范围']]))}
          {values.page_count_mode === 'custom_range' && <div className="create-field-grid"><Form.Item name="min_pages" label="最少页数"><InputNumber aria-label="最少页数" min={5} max={50} precision={0} /></Form.Item><Form.Item name="max_pages" label="最多页数"><InputNumber aria-label="最多页数" min={5} max={50} precision={0} /></Form.Item></div>}
          {select('ppt_style', 'PPT 风格', choices([['general', '通用场景'], ['keynote', '发布会'], ['custom', '自定义风格']]))}
          {values.ppt_style === 'custom' && <Form.Item name="custom_style_prompt" label="自定义风格描述" rules={[{ required: true, whitespace: true, message: '请填写自定义风格描述' }]}><Input.TextArea aria-label="自定义风格描述" autoSize={{ minRows: 2, maxRows: 6 }} /></Form.Item>}
          <div className="create-field-grid">{select('language', '语言', choices([['zh', '中文'], ['en', 'English']]))}
            {select('render_mode', '页面绘制方式', choices([['html', 'HTML（默认）'], ['svg', 'SVG（实验）']]), fast)}
          </div>
        </Card>
      </div>
      {error && <Alert className="page-error" type="error" title={error} description={redirect ? <span>项目已创建，可<a href={redirect}>前往看板</a>手动确认需求，避免重复创建。</span> : undefined} showIcon />}
      <div className="create-submit-bar"><span className="subtle">{pending ? '正在创建项目…' : 'Ctrl / ⌘ + Enter'}</span><Button type="primary" htmlType="submit" aria-label="开始生成" aria-busy={pending} icon={<ArrowRightOutlined aria-hidden />} loading={pending} disabled={pending || (fast && (packageLoading || !!packageError))}>开始生成</Button></div>
    </Form>
  </div>;
}
