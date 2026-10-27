import { useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Card, Empty, Form, Input, Select, Space, Spin, Tag } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { request, type ApiData } from '../api';
import { ImageActions, ImagePreview } from '../components/images';
import { useAdminActions } from '../components/admin-data';

const providers = [
  { value: 'dalle', label: 'DALL-E 3' }, { value: 'openai_image', label: 'OpenAI 图片' }, { value: 'gemini', label: 'Gemini' },
  { value: 'siliconflow', label: 'SiliconFlow' }, { value: 'stable_diffusion', label: 'Stable Diffusion' },
];
const dimensions = [
  ['1024x1024', '1024 × 1024 · 正方形'], ['1792x1024', '1792 × 1024 · 横向'], ['1024x1792', '1024 × 1792 · 竖向'],
  ['1536x1024', '1536 × 1024 · 横向'], ['1024x1536', '1024 × 1536 · 竖向'], ['1280x720', '1280 × 720 · HD'],
].map(([value, label]) => ({ value, label }));
const providerName = (value: string) => providers.find(item => item.value === value)?.label || value;
const historyKey = 'imageGenerationHistory';
type HistoryItem = { id: number; imageUrl: string; prompt: string; provider: string; timestamp: string };
type Result = HistoryItem & { elapsed?: number };

function imageURL(value: unknown) {
  const path = String(value || '');
  if (!path) return '';
  // API paths use the current site origin, including width/height query params.
  if (/^https?:\/\//i.test(path)) { try { const url = new URL(path); return url.pathname + url.search + url.hash; } catch { return ''; } }
  if (path.startsWith('/') && !path.startsWith('//')) return path;
  return path.includes(':') || path.startsWith('//') ? '' : '/images/' + path;
}
function readHistory(): HistoryItem[] {
  try {
    const data = JSON.parse(localStorage.getItem(historyKey) || '[]');
    return Array.isArray(data) ? data.filter(item => item && typeof item.id === 'number' && typeof item.prompt === 'string' && typeof item.provider === 'string' && typeof item.timestamp === 'string' && imageURL(item.imageUrl)).slice(0, 20).map(item => ({ ...item, imageUrl: imageURL(item.imageUrl) })) : [];
  } catch { return []; }
}

export default function ImageGeneration() {
  const { message } = App.useApp(); const actions = useAdminActions(); const [form] = Form.useForm();
  const [status, setStatus] = useState<ApiData>(); const [statusError, setStatusError] = useState(''); const [refresh, setRefresh] = useState(0); const [statusLoading, setStatusLoading] = useState(true);
  const [result, setResult] = useState<Result>(); const [history, setHistory] = useState(readHistory); const [historyWarning, setHistoryWarning] = useState('');
  const [pending, setPending] = useState(false); const [error, setError] = useState(''); const [elapsed, setElapsed] = useState(0); const locked = useRef(false);
  const provider = Form.useWatch('provider', form);
  const sizeOptions = provider === 'gemini' ? dimensions : ['dalle', 'openai_image'].includes(provider) ? dimensions.slice(0, 3) : dimensions.slice(0, 5);
  useEffect(() => {
    const controller = new AbortController(); setStatusLoading(true); setStatusError('');
    request('/api/image/status', 'GET', undefined, controller.signal).then(data => { if (!controller.signal.aborted) setStatus(data); })
      .catch(reason => { if (!controller.signal.aborted) setStatusError(reason.message); }).finally(() => { if (!controller.signal.aborted) setStatusLoading(false); });
    return () => controller.abort();
  }, [refresh]);
  useEffect(() => {
    if (!pending) return;
    const start = Date.now(); setElapsed(0); const timer = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [pending]);
  function saveHistory(items: HistoryItem[]) {
    setHistory(items);
    try { localStorage.setItem(historyKey, JSON.stringify(items)); setHistoryWarning(''); }
    catch { setHistoryWarning('浏览器无法保存历史记录，本次结果仍可查看和下载。'); }
  }
  async function generate(values: ApiData) {
    if (locked.current) return;
    locked.current = true; setPending(true); setError(''); const start = Date.now();
    const [width, height] = values.size.split('x').map(Number);
    try {
      const data = await request('/api/image/generate', 'POST', { prompt: values.prompt, provider: values.provider, width, height, quality: values.provider === 'gemini' ? null : values.quality });
      const url = imageURL(data.image_path || data.image_info?.local_path);
      if (!url) throw new Error('生成结果缺少有效的图片链接，请重试。');
      const item = { id: Date.now(), imageUrl: url, prompt: values.prompt, provider: values.provider, timestamp: new Date().toLocaleString('zh-CN') };
      setResult({ ...item, elapsed: Math.floor((Date.now() - start) / 1000) }); saveHistory([item, ...history].slice(0, 20));
    } catch (reason) { setError((reason as Error).message); }
    finally { locked.current = false; setPending(false); }
  }
  return <div className="image-generation-page settings-stack">
    <div className="page-heading"><h1>AI 图片生成</h1><Button href="/image-gallery">返回图库</Button></div>
    <Card size="small" title="提供者状态" extra={<Button aria-label="刷新提供者状态" icon={<ReloadOutlined />} loading={statusLoading} onClick={() => setRefresh(value => value + 1)} />}>
      {statusError && <Alert type="error" title="状态加载失败" description={statusError} action={<Button onClick={() => setRefresh(value => value + 1)}>重试</Button>} />}
      {statusLoading && <p role="status"><Spin size="small" /> 正在加载状态…</p>}
      {status && <><div className="image-provider-grid">{providers.map(item => <div className="image-provider" key={item.value}><span>{item.label}</span><Tag color={status.available_providers?.includes(item.value) ? 'success' : undefined}>{status.available_providers?.includes(item.value) ? '可用' : '未配置'}</Tag></div>)}</div>{status.status === 'disabled' && <Alert className="image-service-notice" type="warning" title="图片服务未启用，请在系统配置中检查设置。" action={<Button href="/ai-config#image-service">配置</Button>} />}</>}
    </Card>
    <div className="image-generation-grid"><Card size="small" title="生成参数"><Form form={form} layout="vertical" initialValues={{ provider: '', size: '1792x1024', quality: 'standard', prompt: '' }} disabled={pending} onFinish={generate}>
      <Form.Item name="prompt" label="提示词" rules={[{ required: true, whitespace: true, message: '请输入提示词' }]}><Input.TextArea aria-label="提示词" rows={4} placeholder="描述画面内容、风格和构图" /></Form.Item>
      <Form.Item name="provider" label="AI 提供者" rules={[{ required: true, message: '请选择 AI 提供者' }]}><Select aria-label="AI 提供者" placeholder="选择提供者" options={providers} onChange={() => form.setFieldValue('size', '1792x1024')} /></Form.Item>
      <div className="image-generation-options"><Form.Item name="size" label="图片尺寸"><Select options={sizeOptions} /></Form.Item><Form.Item name="quality" label="图片质量"><Select disabled={pending || provider === 'gemini'} options={[{ value: 'standard', label: '标准' }, { value: 'hd', label: '高清' }]} /></Form.Item></div>
      <Button block type="primary" htmlType="submit" aria-label="生成图片" disabled={pending} loading={pending}>生成图片</Button>
      {pending && <p role="status" className="image-generating">正在生成，已用时 {elapsed} 秒…</p>}
    </Form></Card>
      <Card size="small" title="生成结果"><div className="image-result" aria-busy={pending}>
        {error && <Alert type="error" title="图片生成失败" description={error} />}
        {result ? <><div className="image-result-meta"><Tag color="success">{result.elapsed === undefined ? '历史结果' : '生成成功'}</Tag><span>{providerName(result.provider)}{result.elapsed !== undefined && ` · ${result.elapsed} 秒`}</span></div>
          <ImagePreview src={result.imageUrl} title={result.prompt} /><p className="image-result-prompt">{result.prompt}</p><ImageActions url={result.imageUrl} /></>
          : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="生成后的图片将在这里显示" />}
      </div></Card>
    </div>
    <Card size="small" title="生成历史" extra={<Button disabled={!history.length || pending} onClick={() => actions.confirm('清空生成历史', '只清除当前浏览器中的记录，图库图片会保留。', async () => {
      try { localStorage.removeItem(historyKey); setHistoryWarning(''); } catch { setHistoryWarning('浏览器存储不可用，刷新后旧记录可能再次出现。'); }
      setHistory([]); message.success('生成历史已清空');
    }, true)}>清空历史</Button>}>
      {historyWarning && <Alert type="warning" title={historyWarning} />}
      {history.length ? <div className="image-history-grid">{history.map(item => <button className="image-history-item" key={item.id} aria-label={`查看历史：${item.prompt}`} disabled={pending} onClick={() => {
        form.setFieldsValue({ prompt: item.prompt, provider: item.provider, size: '1792x1024' }); setResult(item); setError(''); window.scrollTo({ top: 0 });
      }}><img src={item.imageUrl} alt={item.prompt} loading="lazy" onError={event => { event.currentTarget.onerror = null; event.currentTarget.src = '/static/images/placeholder.svg'; }} /><span className="image-history-caption"><strong>{item.prompt}</strong><span>{providerName(item.provider)} · {item.timestamp}</span></span></button>)}</div> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无生成记录" />}
    </Card>
  </div>;
}
