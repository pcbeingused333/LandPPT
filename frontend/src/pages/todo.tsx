import { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Button, Card, Checkbox, Collapse, Form, Input, InputNumber, Select, Space, Tabs, Tag, Upload } from 'antd';
import { EyeOutlined, InboxOutlined, ReloadOutlined } from '@ant-design/icons';
import { errorText, request, type ApiData } from '../api';
import { useNativeFeedback } from '../components/native-feedback';
import { UnattendedPanel } from '../components/unattended';
import { TodoOutline } from '../components/todo-outline';
import { ProjectStages, ProjectWorkspaceHeader } from '../components/project-stages';
import { createOutlineController } from '../controllers/outline-controller';

const audience = ['企业管理层', '技术团队', '销售团队', '学生群体', '学术研究者', '投资人', '客户群体', '培训学员', '项目团队', '行业专家', '普通大众', '自定义'].map(value => ({ value, label: value === '自定义' ? '自定义受众' : value }));
const extensions = ['pdf', 'docx', 'txt', 'md', 'jpg', 'jpeg', 'png', 'xlsx', 'csv'];
const options = (items: string[][]) => items.map(([value, label]) => ({ value, label }));
function parseUrls(raw: string) {
  const unique = new Set<string>();
  String(raw || '').split(/[\n,;\t ]+/).filter(Boolean).forEach(value => {
    try { const url = new URL(/^https?:\/\//i.test(value) ? value : `https://${value}`); if (['http:', 'https:'].includes(url.protocol)) unique.add(url.href); } catch { /* Ignore invalid candidates, matching the existing parser. */ }
  });
  return [...unique].slice(0, 50);
}

export default function Todo({ data }: { data: ApiData }) {
  useNativeFeedback();
  const [form] = Form.useForm();
  const initial = { topic: String(data.title || '').split(' - ')[0], audience_type: '', custom_audience: '', page_count_mode: 'ai_decide', min_pages: 8, max_pages: 15, ppt_style: 'general', custom_style_prompt: '', render_mode: data.renderMode || 'html', generation_mode: 'freeform', package_version_id: '', include_transition_pages: false, include_page_numbers: true, file_processing_mode: 'markitdown', content_analysis_depth: 'fast', content_urls: '' };
  const fields = { ...initial, ...Form.useWatch(values => values, form) };
  const [confirmed, setConfirmed] = useState(!data.showRequirements);
  const [pending, setPending] = useState(false);
  const [source, setSource] = useState('manual');
  const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState(''); const [warning, setWarning] = useState('');
  const [packages, setPackages] = useState<ApiData[]>([]);
  const [packageError, setPackageError] = useState(''); const [packageLoading, setPackageLoading] = useState(false); const [revision, setRevision] = useState(0);
  const locked = useRef(false);
  const readOnly = !!data.workspace?.generating || !!data.workspace?.outlineRunning && !!data.hasOutline;
  const outlineController = useMemo(() => createOutlineController({ projectId: data.projectId, ...data.outlineInitial, hasOutput: !!data.hasOutput, unattended: !!data.unattendedActive, readOnly }), [data, readOnly]);
  const reloading = useRef(false);
  const reloadTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const fast = fields.generation_mode === 'package';
  const base = `/projects/${encodeURIComponent(data.projectId)}`;
  useEffect(() => {
    const visibility = () => outlineController.setVisible(!document.hidden);
    const hide = () => outlineController.suspend();
    const show = (event: PageTransitionEvent) => { if (event.persisted) outlineController.resume(); };
    outlineController.setVisible(!document.hidden); outlineController.mount();
    document.addEventListener('visibilitychange', visibility);
    window.addEventListener('pagehide', hide); window.addEventListener('pageshow', show);
    return () => {
      outlineController.dispose(); clearTimeout(reloadTimer.current);
      document.removeEventListener('visibilitychange', visibility);
      window.removeEventListener('pagehide', hide); window.removeEventListener('pageshow', show);
    };
  }, [outlineController]);
  useEffect(() => {
    if (!fast) return;
    const controller = new AbortController(); setPackageLoading(true); setPackageError('');
    request('/api/global-master-templates/packages', 'GET', undefined, controller.signal).then(result => {
      if (controller.signal.aborted) return;
      if (!Array.isArray(result.packages)) throw new Error('模板包列表无效，请重试');
      const published = result.packages.filter(item => item.status === 'published'); setPackages(published);
      if (!published.some(item => String(item.id) === form.getFieldValue('package_version_id'))) form.setFieldValue('package_version_id', '');
    }).catch(reason => { if (!controller.signal.aborted) setPackageError(reason.message); }).finally(() => { if (!controller.signal.aborted) setPackageLoading(false); });
    return () => controller.abort();
  }, [fast, revision, form]);
  function reloadSoon(delay: number) {
    if (reloading.current) return;
    reloading.current = true; reloadTimer.current = setTimeout(() => location.reload(), delay);
  }
  function addFile(file: File) {
    if (!extensions.includes(file.name.split('.').pop()?.toLowerCase() || '')) setWarning(`不支持的文件类型：${file.name}`);
    else if (file.size > 100 * 1024 * 1024) setWarning(`文件超过 100MB：${file.name}`);
    else setFiles(current => current.some(item => item.name === file.name && item.size === file.size) ? current : [...current, file]);
    return false;
  }
  async function submit(input: ApiData) {
    if (locked.current || data.unattendedActive || readOnly) return;
    setError('');
    const values = { ...initial, ...form.getFieldsValue(true), ...input };
    if (source === 'file' && !files.length) { setError('请至少选择一个文件。'); return; }
    const urls = parseUrls(values.content_urls);
    if (source === 'url' && !urls.length) { setError('请至少提供一个有效 URL（http/https）。'); return; }
    if (fast && (packageLoading || packageError || !packages.some(item => String(item.id) === values.package_version_id))) { setError('快速模式需要先选择一个已发布的模板包。'); return; }
    if (values.page_count_mode === 'custom_range' && values.min_pages > values.max_pages) { setError('最少页数不能大于最多页数。'); return; }
    const body = new FormData();
    Object.entries(values).filter(([key]) => key !== 'content_urls' && key !== 'package_version_id').forEach(([key, value]) => body.append(key, String(value ?? '').trim()));
    body.set('content_source', source); body.set('package_version_id', fast ? values.package_version_id : '0'); body.set('render_mode', fast ? 'svg' : values.render_mode);
    if (source === 'url') body.set('content_urls', urls.join('\n'));
    if (source === 'file') files.forEach(file => body.append('file_upload', file));
    locked.current = true; setPending(true);
    try {
      const response = await fetch(`${base}/confirm-requirements`, { method: 'POST', credentials: 'same-origin', headers: { Accept: 'application/json' }, body });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || result.status !== 'success') throw new Error(errorText(result.detail || result.message || `需求确认失败（HTTP ${response.status}）`));
      setConfirmed(true); void outlineController.beginOutline();
    } catch (reason) { setError((reason as Error).message); }
    finally { locked.current = false; setPending(false); }
  }
  const select = (name: string, label: string, choices: { value: string; label: string }[], required = false) => <Form.Item name={name} label={label} rules={required ? [{ required: true, message: `请选择${label}` }] : []}><Select aria-label={label} options={choices} virtual={false} /></Form.Item>;
  return <div className="todo-ant-page">
    <ProjectWorkspaceHeader back={{ href: base, label: '返回项目详情' }} title={data.title}
      meta={<><Tag>{data.generationMode === 'package' ? '快速模式 · 模板包' : '自由设计'}</Tag>{!readOnly && !data.hasOutput && <span className="subtle project-workspace-hint">{data.hasOutline ? '确认大纲后进入视觉设计。' : '先确认需求，再生成并修改大纲。'}</span>}<a href="/ai-config#jev-config">决策模型配置</a></>}
      actions={(data.hasOutline || data.hasOutput) && <Space wrap>{data.hasOutline && <Button href={`${base}/template-selection?mode=package`}>快速模式设置</Button>}{data.hasOutput && <Button href={`${base}/preview`} target="_blank" rel="noopener" icon={<EyeOutlined aria-hidden />}>预览 PPT</Button>}</Space>}
      stages={<ProjectStages projectId={data.projectId} state={data.workspace} current="planning" />} />
    {(readOnly || data.hasOutput) && <Alert showIcon type="info" className="page-error" title={readOnly ? '生成任务进行中，可查看大纲，完成后再编辑。' : '大纲修改不会自动更新已生成页面，请在编辑器中调整页面。'} />}
    <div id="unattendedMonitor"><UnattendedPanel projectId={data.projectId} initiallyActive={!!data.unattendedActive} onUpdate={run => { if (!data.hasOutline && run.stages?.some((stage: ApiData) => stage.id === 'outline' && stage.status === 'completed')) reloadSoon(600); }} onComplete={run => reloadSoon(run.task_status === 'completed' ? 1500 : 6000)} /></div>
    {!confirmed && !data.unattendedActive && <Form form={form} name="todo-requirements" layout="vertical" initialValues={initial} disabled={pending || readOnly} onFinish={submit} scrollToFirstError={{ focus: true }}>
      <div className="todo-ant-form-grid"><Card size="small" title="内容与受众">
        <Tabs activeKey={source} onChange={value => { if (!pending) setSource(value); }} items={[
          { key: 'manual', label: '输入主题', children: <p className="subtle">根据主题和已保存的具体需求生成大纲。</p> },
          { key: 'file', label: '上传文件', children: <><Upload.Dragger multiple accept={extensions.map(ext => '.' + ext).join(',')} beforeUpload={addFile} showUploadList={false}><p><InboxOutlined aria-hidden /></p><p>选择或拖入资料文件</p><p className="subtle">PDF、Word、文本、图片与表格，单个文件不超过 100MB。</p></Upload.Dragger><ul className="todo-ant-files">{files.map((file, index) => <li key={`${file.name}-${file.size}`}><span title={file.name}>{file.name}</span><Button size="small" aria-label={`移除文件 ${file.name}`} onClick={() => setFiles(current => current.filter((_, i) => i !== index))}>移除</Button></li>)}</ul>{files.length > 0 && <Button onClick={() => setFiles([])}>清空文件</Button>}</> },
          { key: 'url', label: '网页链接', children: <Form.Item name="content_urls" label="内容链接" extra={`每行一个或逗号分隔，最多50个；已识别 ${parseUrls(fields.content_urls).length} 个。`}><Input.TextArea aria-label="内容链接" autoSize={{ minRows: 3, maxRows: 5 }} placeholder="https://example.com/article" /></Form.Item> },
        ]} />
        {warning && <Alert type="warning" title={warning} closable onClose={() => setWarning('')} />}
        <Form.Item name="topic" label="主题" rules={source === 'file' ? [] : [{ required: true, whitespace: true, message: '请输入主题' }]}><Input aria-label="主题" placeholder={source === 'file' ? '可留空，自动从文件提取' : '请输入演示主题'} /></Form.Item>
        {select('audience_type', '目标受众', audience, true)}
        {fields.audience_type === '自定义' && <Form.Item name="custom_audience" label="自定义受众" rules={[{ required: true, whitespace: true, message: '请描述自定义受众' }]}><Input aria-label="自定义受众" /></Form.Item>}
        {source !== 'manual' && <Collapse size="small" items={[{ key: 'parsing', label: '资料解析选项', children: <>{select('file_processing_mode', 'PDF 处理方式', options([['markitdown','标准处理 · MarkItDown'], ['magic_pdf','高质量 · Mineru（提取图片）']]))}{select('content_analysis_depth','解析深度',options([['fast','快速解析'],['standard','标准解析'],['deep','深度解析']]))}</> }]} />}
      </Card><Card size="small" title="页数与设计">
        {select('page_count_mode','页数设置',options([['ai_decide','AI 智能决定'],['custom_range','自定义范围']]))}
        {fields.page_count_mode === 'custom_range' && <div className="create-field-grid"><Form.Item name="min_pages" label="最少页数" rules={[{ required: true }]}><InputNumber aria-label="最少页数" min={5} max={50} precision={0} /></Form.Item><Form.Item name="max_pages" label="最多页数" rules={[{ required: true }]}><InputNumber aria-label="最多页数" min={5} max={50} precision={0} /></Form.Item></div>}
        {select('ppt_style','演示风格',options([['general','通用场景'],['keynote','发布会'],['custom','自定义风格']]))}
        {fields.ppt_style === 'custom' && <Form.Item name="custom_style_prompt" label="自定义风格描述" rules={[{ required: true, whitespace: true, message: '请填写风格描述' }]}><Input.TextArea aria-label="自定义风格描述" autoSize={{ minRows: 2, maxRows: 4 }} /></Form.Item>}
        {select('generation_mode','生成方式',options([['freeform','自由设计'],['package','快速模式 · 模板包']]))}
        {fast ? <><Form.Item name="package_version_id" label="已发布模板包"><Select aria-label="已发布模板包" disabled={packageLoading || !!packageError} loading={packageLoading} options={packages.map(item => ({ value: String(item.id), label: `${item.template_name} · v${item.version}` }))} /></Form.Item>{packageError && <Alert type="error" title={packageError} action={<Button icon={<ReloadOutlined aria-hidden />} onClick={() => setRevision(value => value + 1)}>重试</Button>} />}<p className="subtle">快速模式使用 SVG 页面，按模板包规划内容与版式。</p></> : select('render_mode','页面绘制方式',options([['html','HTML 页面'],['svg','SVG 页面（实验）']]))}
        <Space wrap><Form.Item name="include_transition_pages" valuePropName="checked" className="create-checkbox"><Checkbox>章节过渡页</Checkbox></Form.Item><Form.Item name="include_page_numbers" valuePropName="checked" className="create-checkbox"><Checkbox>页码 / Footer</Checkbox></Form.Item></Space>
      </Card></div>
      {error && <Alert type="error" title="需求确认失败" description={error} className="page-error" />}
      <div className="todo-ant-submit"><span className="subtle">确认后开始生成，可实时查看并编辑大纲。</span><Button type="primary" htmlType="submit" aria-label="开始生成大纲" loading={pending} disabled={pending || readOnly || fast && (packageLoading || !!packageError)} aria-busy={pending}>开始生成大纲</Button></div>
    </Form>}
    <TodoOutline projectId={data.projectId} unattendedActive={!!data.unattendedActive} readOnly={readOnly} controller={outlineController} />
  </div>;
}
