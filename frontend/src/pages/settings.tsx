import { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, App, AutoComplete, Button, Card, Collapse, Form, Input, InputNumber, Modal, Radio, Select, Slider, Space, Switch, Tabs, Tag } from 'antd';
import { ReloadOutlined, SaveOutlined, ApiOutlined } from '@ant-design/icons';
import { request, type ApiData } from '../api';
import { readSettingsSchema, type Field } from '../settings-schema';
import JevSettings from './jev-settings';
import { modalFocus } from '../components/modal-focus';

const categories: Record<string, string> = { 'generation-params': 'generation_params', 'app-config': 'app_config', 'image-service': 'image_service' };
const saveLabels: Record<string, string> = { 'generation-params': '保存生成参数', 'app-config': '保存应用配置', 'image-service': '保存配置' };
const bool = (value: unknown) => value === true || value === 1 || value === 'true' || value === '1';
const labels: Record<string, string> = { landppt: 'LandPPT', openai: 'OpenAI', anthropic: 'Anthropic Claude', google: 'Google Gemini' };

export default function Settings({ data }: { data: ApiData }) {
  const panels = useMemo(readSettingsSchema, []);
  const allFields = useMemo(() => panels.flatMap(panel => panel.fields), [panels]);
  const initial = useMemo(() => Object.fromEntries(allFields.map(field => [field.name, data.config[field.name] ?? field.value])), [allFields, data.config]);
  const [values, setValues] = useState<ApiData>(initial);
  const valuesRef = useRef(values); valuesRef.current = values;
  const dirty = useRef(new Set<string>());
  const [active, setActive] = useState('ai-providers');
  const [defaultProvider, setDefaultProvider] = useState(data.currentProvider);
  const [pending, setPending] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [models, setModels] = useState<Record<string, { label: string; value: string }[]>>({});
  const [imageStatus, setImageStatus] = useState<ApiData>({});
  const [testResult, setTestResult] = useState<ApiData | null>(null);
  const testTrigger = useRef<HTMLElement | null>(null);
  const { message } = App.useApp();
  const operations = useRef(new Map<string, AbortController>());
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    request('/api/config/all', 'GET', undefined, controller.signal).then(result => {
      setValues(previous => {
        const next = { ...previous };
        allFields.forEach(field => {
          if (!dirty.current.has(field.name) && Object.hasOwn(result.config || {}, field.name)) next[field.name] = result.config[field.name];
        });
        return next;
      });
    }).catch(reason => { if (!controller.signal.aborted) setError(`配置读取失败：${reason.message}`); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    request('/api/image/status', 'GET', undefined, controller.signal).then(setImageStatus).catch(() => {});
    return () => { mounted.current = false; controller.abort(); operations.current.forEach(operation => operation.abort()); operations.current.clear(); };
  }, [allFields]);
  function change(name: string, value: unknown) {
    dirty.current.add(name);
    setValues(previous => ({ ...previous, [name]: value }));
    setFieldErrors(previous => { const next = { ...previous }; delete next[name]; return next; });
  }
  async function run(key: string, operation: (signal: AbortSignal) => Promise<void>) {
    if (operations.current.size) return;
    if (key.startsWith('test-')) testTrigger.current = document.activeElement as HTMLElement;
    const controller = new AbortController(); operations.current.set(key, controller);
    setPending(key); setError('');
    try { await operation(controller.signal); }
    catch (reason) { if (!controller.signal.aborted && mounted.current) setError((reason as Error).message); }
    finally { operations.current.delete(key); if (mounted.current) setPending(''); }
  }
  function payload(fields: Field[], category: string): ApiData | null {
    const config: ApiData = {}; const errors: Record<string, string> = {};
    fields.forEach(field => {
      const value = valuesRef.current[field.name];
      if (field.kind === 'checkbox') { config[field.name] = bool(value); return; }
      let text = String(value ?? '');
      if (category !== 'generation_params') text = text.trim();
      if (field.name === 'tavily_base_url') text = text.trim() || 'https://api.tavily.com';
      if (field.required && !text.trim()) errors[field.name] = '请填写此项';
      if (field.kind === 'number' && text && (!Number.isFinite(Number(text)) || (field.min !== undefined && Number(text) < field.min) || (field.max !== undefined && Number(text) > field.max))) errors[field.name] = `请输入 ${field.min ?? '有效数值'} 至 ${field.max ?? '有效数值'} 之间的数值`;
      if (field.name === 'ai_image_resolution_presets' && text.trim()) {
        try { JSON.parse(text); } catch { errors[field.name] = '请输入有效的 JSON'; }
      }
      if (category === 'image_service' && field.kind === 'textarea') text = text.replace(/[\r\n]+/g, ' ');
      if (text || category === 'model_roles') config[field.name] = text;
    });
    setFieldErrors(errors);
    if (Object.keys(errors).length) { setError('请检查标记的配置项后保存。'); document.getElementById(`field-${Object.keys(errors)[0]}`)?.focus(); return null; }
    return config;
  }
  function save(fields: Field[], category: string, key: string) {
    const config = payload(fields, category); if (!config) return;
    run(key, async signal => {
      if (category === 'ai_providers' && fields.some(field => field.name === 'landppt_model') && !config.landppt_model) {
        try { const result = await request('/api/ai/providers/landppt/models', 'GET', undefined, signal); config.landppt_model = result.models?.includes('MODEL1') ? 'MODEL1' : result.models?.[0] || 'MODEL1'; }
        catch (reason) { if (signal.aborted) throw reason; config.landppt_model = 'MODEL1'; }
      }
      await request(`/api/config/${category}`, 'POST', { config }, signal);
      fields.forEach(field => dirty.current.delete(field.name));
      setValues(previous => ({ ...previous, ...config }));
      message.success('配置已保存，已实时生效');
      if (category === 'image_service') request('/api/image/status', 'GET', undefined, signal).then(setImageStatus).catch(() => {});
    });
  }
  function testProvider(provider: string) {
    const config = valuesRef.current;
    const body: ApiData = { provider };
    ['api_key', 'base_url', 'model'].forEach(key => { if (config[`${provider}_${key}`]) body[key] = String(config[`${provider}_${key}`]).trim(); });
    if (provider === 'openai') body.use_responses_api = bool(config.openai_use_responses_api);
    if (['openai', 'anthropic'].includes(provider)) { body.enable_reasoning = bool(config[`${provider}_enable_reasoning`]); body.reasoning_effort = config[`${provider}_reasoning_effort`] || 'medium'; }
    run(`test-${provider}`, async signal => { const result = await request('/api/ai/providers/test', 'POST', body, signal); setTestResult({ title: `${labels[provider]} 连接测试`, message: result.message || '连接成功' }); });
  }
  async function fetchModels(field: Field) {
    const provider = field.name === 'pollinations_model' ? 'pollinations' : field.name.endsWith('_model_name') ? String(valuesRef.current[field.name.replace('_name', '_provider')] || defaultProvider) : field.name.replace('_model', '');
    await run(`models-${field.name}`, async signal => {
      let list: string[] = [];
      const names = (records: unknown[]) => records
        .filter((model: any) => provider !== 'pollinations' || (typeof model === 'object' && Array.isArray(model?.output_modalities) && model.output_modalities.includes('image')))
        .map((model: any) => typeof model === 'string' ? model : model.id || model.name).filter(Boolean);
      if (provider === 'landppt') list = (await request('/api/ai/providers/landppt/models', 'GET', undefined, signal)).models || [];
      else {
        let config = valuesRef.current;
        if (!config[`${provider}_api_key`]) {
          const saved = await request(`/api/config/${provider === 'pollinations' ? 'image_service' : 'ai_providers'}`, 'GET', undefined, signal);
          config = { ...saved.config, ...Object.fromEntries(Object.entries(config).filter(([, value]) => String(value ?? '').trim())) };
        }
        const base = String(config[`${provider}_${provider === 'pollinations' ? 'api_base' : 'base_url'}`] || (provider === 'openai' ? 'https://api.openai.com/v1' : provider === 'pollinations' ? 'https://gen.pollinations.ai' : '')).replace(/\/$/, '');
        if (!config[`${provider}_api_key`] && provider !== 'pollinations') throw new Error('请先配置 API Key');
        try {
          const response = await fetch(`${base}/${provider === 'pollinations' ? 'image/models' : 'models'}`, { signal, headers: config[`${provider}_api_key`] ? { Authorization: `Bearer ${config[`${provider}_api_key`]}` } : {} });
          if (!response.ok) throw new Error(`模型列表读取失败（${response.status}）`);
          const result = await response.json();
          list = names(Array.isArray(result) ? result : result.data || []);
        } catch (reason) {
          if (signal.aborted || provider !== 'pollinations') throw reason;
          const result = await request('/api/image/pollinations/models', 'GET', undefined, signal);
          list = names(Array.isArray(result) ? result : result.models || []);
        }
      }
      list.sort((a, b) => a.localeCompare(b));
      if (list.includes('MODEL1')) list = ['MODEL1', ...list.filter(model => model !== 'MODEL1')];
      setModels(previous => ({ ...previous, [field.name]: [...(provider === 'pollinations' ? [{ label: '（留空/默认）', value: '' }] : []), ...list.map(model => ({ label: model, value: model }))] }));
      message.success(list.length ? `已获取 ${list.length} 个模型` : '暂无可用模型，可手动填写');
    });
  }
  function renderField(field: Field) {
    if (field.dependencies.some(name => !bool(values[name]))) return null;
    const id = `field-${field.name}`;
    const raw = values[field.name];
    const value = String(raw ?? '');
    const modelField = field.name.endsWith('_model') || field.name.endsWith('_model_name');
    const reasoning = field.name.endsWith('_reasoning_effort');
    const disabled = !!pending || (reasoning && !bool(values[field.name.replace('_reasoning_effort', '_enable_reasoning')]));
    const common = { id, 'aria-label': field.label, placeholder: field.placeholder, disabled };
    if (field.kind === 'checkbox') return <Form.Item key={field.name} className="switch-field"><label className="switch-row" htmlFor={id}><span className="switch-copy"><span>{field.label}</span>{field.help && <span className="subtle">{field.help}</span>}</span><Switch id={id} aria-label={field.label} disabled={!!pending} checked={bool(raw)} onChange={checked => change(field.name, checked)} /></label></Form.Item>;
    let control;
    if (field.kind === 'select') control = <Select {...common} value={value} options={models[field.name] || field.options} onChange={next => change(field.name, next)} showSearch optionFilterProp="label" />;
    else if (field.kind === 'number') control = <><InputNumber {...common} name={field.name} value={value ? Number(value) : null} min={field.min} max={field.max} step={field.step || 1} onChange={next => change(field.name, next === null ? '' : String(next))} />{field.slider && <Slider aria-label={`${field.label}滑块`} {...field.slider} value={value ? Number(value) : field.slider.min} onChange={next => change(field.name, String(next))} />}</>;
    else if (field.kind === 'textarea') control = <Input.TextArea {...common} name={field.name} value={value} autoSize={{ minRows: 3, maxRows: 8 }} onChange={event => change(field.name, event.target.value)} />;
    else if (field.kind === 'password') control = <Input.Password {...common} name={field.name} value={value} autoComplete="new-password" onChange={event => change(field.name, event.target.value)} />;
    else if (modelField || field.options.length) control = <AutoComplete {...common} value={value} options={models[field.name] || field.options.filter(option => option.value)} onChange={next => change(field.name, next)} filterOption={(input, option) => String(option?.value).toLowerCase().includes(input.toLowerCase())}><Input name={field.name} /></AutoComplete>;
    else control = <Input {...common} name={field.name} value={value} onChange={event => change(field.name, event.target.value)} />;
    return <Form.Item key={field.name} label={field.label} htmlFor={id} extra={field.help || undefined} validateStatus={fieldErrors[field.name] ? 'error' : undefined} help={fieldErrors[field.name]} className={field.kind === 'textarea' ? 'field-full' : undefined}>
      {modelField ? <div className="model-control">{control}<Button aria-label={`获取${field.label}列表`} title="获取可用模型列表" disabled={!!pending} loading={pending === `models-${field.name}`} icon={<ReloadOutlined aria-hidden />} onClick={() => fetchModels(field)} /></div> : control}
      {field.name === 'pollinations_model' && <Button className="field-action" disabled={!!pending} loading={pending === `models-${field.name}`} onClick={() => fetchModels(field)} icon={<ReloadOutlined aria-hidden />}>获取模型</Button>}
      {field.name === 'ai_image_resolution_presets' && <Button type="text" className="field-action" onClick={() => change(field.name, String(initial[field.name]))}>重置为默认</Button>}
    </Form.Item>;
  }
  function fieldsGrid(fields: Field[]) { return <Form layout="vertical" className="settings-fields">{fields.map(renderField)}</Form>; }
  function renderPanel(key: string) {
    if (key === 'jev-config') return <JevSettings />;
    const fields = panels.find(panel => panel.key === key)!.fields;
    if (key === 'ai-providers') {
      const providers = Object.keys(labels);
      return <div id={key} className="settings-stack">
        <Card size="small" title="AI 提供者" extra={<Tag>默认：{labels[defaultProvider] || defaultProvider}</Tag>}>
          <Collapse defaultActiveKey={[defaultProvider]} items={providers.map(provider => ({
            key: provider, label: <Space>{labels[provider]}<Tag>{provider === 'landppt' || data.providerStatus[provider] ? '可用' : '未配置'}</Tag></Space>,
            children: <>
              {provider === 'landppt' && <Alert type="info" showIcon title="LandPPT 服务凭据由管理员统一维护，此处仅设置当前账号的模型。" description={data.user?.is_admin ? <a href="/admin/community#system-defaults">前往后台管理 / 系统默认配置</a> : undefined} />}
              {fieldsGrid(fields.filter(field => field.section === provider))}
              <div className="settings-actions"><Radio checked={defaultProvider === provider} disabled={!!pending || loading} onChange={() => run(`default-${provider}`, async signal => { await request('/api/config/default-provider', 'POST', { provider }, signal); setDefaultProvider(provider); message.success('默认提供者已更新'); })}>设为默认</Radio><Space wrap><Button disabled={!!pending || loading} loading={pending === `test-${provider}`} icon={<ApiOutlined aria-hidden />} onClick={() => testProvider(provider)}>测试连接</Button><Button type="primary" disabled={!!pending || loading} loading={pending === `save-${provider}`} onClick={() => save(fields.filter(field => field.section === provider), 'ai_providers', `save-${provider}`)}>保存 {labels[provider]}</Button></Space></div>
            </>,
          }))} />
        </Card>
        <Collapse items={[{ key: 'roles', label: '模型任务配置', children: <>{fieldsGrid(fields.filter(field => field.section === '模型任务配置'))}<Button type="primary" disabled={!!pending || loading} loading={pending === 'roles'} onClick={() => save(fields.filter(field => field.section === '模型任务配置'), 'model_roles', 'roles')}>保存模型任务配置</Button></> }]} />
      </div>;
    }
    const sections = [...new Set(fields.map(field => field.section))];
    return <div id={key} className="settings-stack">
      <div className="settings-savebar"><span className="subtle">{loading ? '正在读取配置…' : '保存后应用当前配置'}</span><Space>{key === 'image-service' && <Button disabled={!!pending || loading} loading={pending === 'test-image'} onClick={() => run('test-image', async signal => {
        const config = valuesRef.current; const provider = config.default_ai_image_provider || 'dalle';
        let size = '1024x1024';
        try { size = JSON.parse(config.ai_image_resolution_presets || '{}')[provider]?.[0] || size; } catch { throw new Error('请先修正分辨率 JSON'); }
        const result = await request('/api/image/test-generate', 'POST', { provider, size, quality: config.ai_image_quality || 'standard', prompt: 'A clean modern presentation test image, abstract business technology background, high quality' }, signal);
        const imagePath = String(result.image_path || result.image_url || result.image?.url || '');
        const image = imagePath.startsWith('http') ? new URL(imagePath).pathname : imagePath.startsWith('/') ? imagePath : imagePath ? `/images/${imagePath}` : '';
        setTestResult({ title: '图片生成测试', message: result.message || '图片生成成功', image });
      })}>测试生成</Button>}<Button type="primary" icon={<SaveOutlined aria-hidden />} disabled={!!pending || loading} loading={pending === key} onClick={() => save(fields, categories[key], key)}>{saveLabels[key]}</Button></Space></div>
      {key === 'image-service' && <Alert type={imageStatus.status === 'ok' ? 'success' : 'warning'} showIcon title={`服务状态：${imageStatus.status === 'ok' && imageStatus.available_providers?.length ? '正常运行' : '服务异常'}`} description={`可用提供者：${(imageStatus.available_providers || []).join('、') || '暂无'}`} />}
      {sections.map(section => <Card size="small" title={section} key={section}>{fieldsGrid(fields.filter(field => field.section === section))}</Card>)}
    </div>;
  }
  return <div className="settings-page">
    <div className="page-heading"><div><h1>系统配置管理</h1><p>管理 AI、生成参数与应用服务</p></div></div>
    {error && <Alert className="page-error" role="alert" type="error" showIcon title={error} closable onClose={() => setError('')} />}
    <Tabs aria-label="系统配置分类" activeKey={active} onChange={setActive} items={panels.map(panel => ({ key: panel.key, label: panel.label, children: renderPanel(panel.key) }))} />
    <Modal title={testResult?.title} modalRender={modalFocus} open={!!testResult} onCancel={() => setTestResult(null)} afterClose={() => testTrigger.current?.focus()} footer={<Button onClick={() => setTestResult(null)}>关闭测试结果</Button>}>
      <p className="test-result-copy">{testResult?.message}</p>{testResult?.image && <img className="test-result-image" src={testResult.image} alt="图片生成测试结果" />}
    </Modal>
  </div>;
}
