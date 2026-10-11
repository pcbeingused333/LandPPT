import { useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Card, Form, Input, InputNumber, Select, Space, Switch } from 'antd';
import { request, type ApiData } from '../api';

const endpoint = '/api/global-master-templates/packages/settings';
const defaults = ['https://api.typesafe.ai/v1/systemone', 'https://api.openai.com/v1/chat/completions'];

export default function JevSettings() {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState('');
  const [configured, setConfigured] = useState(false);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const { message } = App.useApp();
  const controller = useRef<AbortController | null>(null);
  const protocol = Form.useWatch('protocol', form);
  useEffect(() => {
    const load = new AbortController();
    request(endpoint, 'GET', undefined, load.signal).then(settings => {
      setConfigured(Boolean(settings.configured));
      form.setFieldsValue({ enabled: settings.enabled, protocol: settings.protocol || 'jev', model: settings.model || 'jev-latest', endpoint_url: settings.endpoint_url || defaults[0], timeout: settings.timeout ?? 30, retries: settings.retries ?? 2, concurrency: settings.concurrency ?? 1 });
    }).catch(reason => { if (!load.signal.aborted) setError(`配置读取失败：${reason.message}`); }).finally(() => { if (!load.signal.aborted) setLoading(false); });
    return () => { load.abort(); controller.current?.abort(); };
  }, [form]);
  async function submit(testOnly: boolean) {
    if (controller.current || loading) return;
    let values: ApiData;
    try { values = await form.validateFields(); } catch { return; }
    const body: ApiData = { ...values, model: values.model.trim(), endpoint_url: values.endpoint_url.trim() };
    if (!values.api_key?.trim()) delete body.api_key;
    else body.api_key = values.api_key.trim();
    if ((body.enabled || testOnly) && !configured && !body.api_key) { form.setFields([{ name: 'api_key', errors: ['请先填写 API Key'] }]); form.scrollToField('api_key', { focus: true }); return; }
    const operation = new AbortController(); controller.current = operation;
    setPending(testOnly ? 'test' : 'save'); setError(''); setStatus('');
    try {
      const result = await request(endpoint + (testOnly ? '/test' : ''), testOnly ? 'POST' : 'PUT', body, operation.signal);
      if (testOnly) setStatus(`测试成功：${result.model}，耗时 ${result.elapsed_ms} 毫秒。当前表单尚未自动保存。`);
      else { setConfigured(configured || Boolean(body.api_key)); form.setFieldValue('api_key', ''); message.success('决策模型配置已保存'); }
    } catch (reason) { if (!operation.signal.aborted) setError((reason as Error).message); }
    finally { controller.current = null; if (!operation.signal.aborted) setPending(''); }
  }
  return <div id="jev-config" className="settings-stack">
    <Alert showIcon type="info" title="决策模型为快速模式评估并匹配模板版式。关闭后仍可使用当前模型与规则匹配。" />
    {error && <Alert role="alert" type="error" showIcon title={error} />}
    <Card title="决策模型配置" size="small" loading={loading}>
      <Form form={form} layout="vertical" disabled={!!pending} initialValues={{ enabled: false, protocol: 'jev', model: 'jev-latest', endpoint_url: defaults[0], timeout: 30, retries: 2, concurrency: 1 }}>
        <Form.Item name="enabled" label="启用决策模型" valuePropName="checked"><Switch /></Form.Item>
        <div className="settings-fields">
          <Form.Item name="protocol" label="接口协议" rules={[{ required: true }]}><Select options={[{ value: 'jev', label: 'Jev' }, { value: 'openai', label: 'OpenAI 兼容' }]} onChange={value => { const previous = form.getFieldValue('endpoint_url'); if (!previous?.trim() || defaults.includes(previous)) form.setFieldValue('endpoint_url', defaults[value === 'openai' ? 1 : 0]); }} /></Form.Item>
          <Form.Item name="model" label="模型名称" rules={[{ required: true, whitespace: true }, { max: 100 }]}><Input /></Form.Item>
          <Form.Item name="endpoint_url" label="请求地址" extra={`填写完整请求地址，例如 ${protocol === 'openai' ? '/v1/chat/completions' : '/v1/systemone'}；不会自动追加路径。`} rules={[{ required: true }, { type: 'url', message: '请输入有效的 URL' }]}><Input /></Form.Item>
          <Form.Item name="api_key" label="API Key" extra={configured ? '已保存密钥；留空保留，填写新密钥替换。' : '尚未配置 API Key。'}><Input.Password autoComplete="new-password" /></Form.Item>
          <Form.Item name="timeout" label="请求超时（秒）" rules={[{ required: true }]}><InputNumber min={1} max={120} /></Form.Item>
          <Form.Item name="retries" label="失败重试次数" rules={[{ required: true }]}><InputNumber min={0} max={3} /></Form.Item>
          <Form.Item name="concurrency" label="并发请求上限" extra="支持 1–16 个匹配请求；遇到限流会等待重试。" rules={[{ required: true }]}><InputNumber min={1} max={16} /></Form.Item>
        </div>
      </Form>
      <div className="settings-actions"><span role="status" className="subtle">{status}</span><Space><Button disabled={loading || !!pending} loading={pending === 'test'} onClick={() => submit(true)}>测试连接</Button><Button type="primary" disabled={loading || !!pending} loading={pending === 'save'} onClick={() => submit(false)}>保存配置</Button></Space></div>
    </Card>
  </div>;
}
