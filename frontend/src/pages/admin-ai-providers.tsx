import { useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Card, Empty, Form, Input, InputNumber, Modal, Radio, Result, Space, Switch, Tag } from 'antd';
import { ArrowDownOutlined, ArrowUpOutlined, EyeOutlined, PlusOutlined } from '@ant-design/icons';
import { request, type ApiData } from '../api';
import { AdminPage } from '../components/admin';
import { ProviderIdentity, ProviderLinks, type ManagedProvider } from '../components/managed-providers';
import { modalFocus } from '../components/modal-focus';

const defaults = { name: '', logo_url: '', description: '', website_url: '', registration_url: '', base_url: '', default_model: '', recommended_models: '', use_responses_api: false, sort_order: 0, is_active: true };

function ProviderManagement({ data }: { data: ApiData }) {
  const { message } = App.useApp();
  const [providers, setProviders] = useState<ManagedProvider[]>([]); const [loading, setLoading] = useState(true);
  const [error, setError] = useState(''); const [dialogError, setDialogError] = useState('');
  const [pending, setPending] = useState(false); const [editor, setEditor] = useState<ManagedProvider | 'new' | null>(null);
  const [preview, setPreview] = useState<ApiData | null>(null); const [form] = Form.useForm();
  const lock = useRef(false); const reading = useRef<AbortController | null>(null); const drag = useRef<string | null>(null);
  async function load() {
    reading.current?.abort(); const controller = new AbortController(); reading.current = controller;
    setLoading(true); setError('');
    try { const result = await request('/admin/api/ai-providers', 'GET', undefined, controller.signal); if (!controller.signal.aborted) setProviders(result.providers || []); }
    catch (reason) { if (!controller.signal.aborted) setError((reason as Error).message); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  }
  useEffect(() => { load(); return () => reading.current?.abort(); }, []);
  function edit(provider: ManagedProvider | 'new') {
    setEditor(provider); setDialogError(''); form.resetFields();
    form.setFieldsValue(provider === 'new' ? { ...defaults, sort_order: providers.length * 10 } : { ...provider, recommended_models: provider.recommended_models.join('\n') });
  }
  function payload(values: ApiData) {
    return Object.fromEntries(Object.keys(defaults).map(key => [key, key === 'recommended_models' ? String(values[key] || '').split(/[\n,，]+/).map(value => value.trim()).filter(Boolean) : values[key] ?? defaults[key as keyof typeof defaults]]));
  }
  async function save() {
    if (lock.current || !editor) return;
    let values; try { values = await form.validateFields(); } catch { return; }
    lock.current = true; setPending(true); setDialogError('');
    try { await request('/admin/api/ai-providers' + (editor === 'new' ? '' : '/' + editor.id), editor === 'new' ? 'POST' : 'PUT', payload(values)); setEditor(null); await load(); message.success('AI 提供商已保存'); }
    catch (reason) { setDialogError((reason as Error).message); }
    finally { lock.current = false; setPending(false); }
  }
  async function reorder(from: string, to: string) {
    if (lock.current || loading || from === to) return;
    const ids = providers.map(provider => provider.id); const source = ids.indexOf(from); const destination = ids.indexOf(to);
    if (source < 0 || destination < 0) return;
    ids.splice(destination, 0, ids.splice(source, 1)[0]); lock.current = true; setPending(true); setError('');
    try { await request('/admin/api/ai-providers/order', 'POST', { ids }); await load(); message.success('展示顺序已更新'); }
    catch (reason) { setError((reason as Error).message); }
    finally { lock.current = false; setPending(false); }
  }
  const urlRule = { validator: (_: unknown, value: string) => {
    if (!value) return Promise.resolve();
    try { const url = new URL(value); if (['https:', 'http:'].includes(url.protocol) && !url.username && !url.password) return Promise.resolve(); } catch { /* validated below */ }
    return Promise.reject(new Error('请输入 HTTP/HTTPS 地址'));
  } };
  const values = Form.useWatch([], { form, preserve: true }) || defaults;
  const disabled = pending || loading;
  return <AdminPage title="AI提供商管理" description="维护服务资料、接入地址与前台展示顺序" credits={data.creditsEnabled}>
    <Card size="small" title="提供商目录" extra={<Space wrap><Button disabled={disabled} onClick={load}>刷新</Button><Button type="primary" disabled={disabled} icon={<PlusOutlined aria-hidden />} onClick={() => edit('new')}>添加提供商</Button></Space>}>
      <p className="subtle">拖动卡片或使用上下移动调整顺序，也可编辑排序值。每位用户独立配置自己的 API Key。</p>
      {error && <Alert className="page-error" type="error" title={error} action={<Button onClick={load}>重试</Button>} />}
      {!loading && !providers.length && <Empty description="暂无 AI 提供商" />}
      <div className="managed-provider-admin-list" aria-busy={disabled}>{providers.map((provider, index) => <article key={provider.id} className="managed-provider-admin-row" draggable={!disabled} onDragStart={event => { drag.current = provider.id; event.dataTransfer.setData('text/plain', provider.id); }} onDragEnd={() => { drag.current = null; }} onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); if (drag.current) reorder(drag.current, provider.id); drag.current = null; }}>
        <div className="managed-provider-heading"><ProviderIdentity provider={provider} /><Space><Tag>{provider.is_active ? '已启用' : '已停用'}</Tag><span className="subtle">排序 {provider.sort_order}</span></Space></div>
        <p className="managed-provider-description">{provider.description || '尚未填写简介'}</p><span className="managed-provider-base">{provider.base_url}</span>
        <div className="managed-provider-heading"><ProviderLinks provider={provider} /><Space wrap><Button aria-label={`上移 ${provider.name}`} icon={<ArrowUpOutlined aria-hidden />} disabled={disabled || index === 0} onClick={() => reorder(provider.id, providers[index - 1].id)} /><Button aria-label={`下移 ${provider.name}`} icon={<ArrowDownOutlined aria-hidden />} disabled={disabled || index === providers.length - 1} onClick={() => reorder(provider.id, providers[index + 1].id)} /><Button icon={<EyeOutlined aria-hidden />} onClick={() => setPreview(provider)}>预览</Button><Button disabled={disabled} onClick={() => edit(provider)}>编辑</Button></Space></div>
      </article>)}</div>
    </Card>
    <Modal title={editor === 'new' ? '添加 AI 提供商' : '编辑 AI 提供商'} open={!!editor} width={720} onCancel={() => { if (!pending) setEditor(null); }} maskClosable={false} closable={!pending} keyboard={!pending} confirmLoading={pending} okText="保存提供商" cancelText="取消" cancelButtonProps={{ disabled: pending }} onOk={save} modalRender={modalFocus}>
      {dialogError && <Alert className="page-error" type="error" title={dialogError} />}
      <Form form={form} layout="vertical" disabled={pending} initialValues={defaults}>
        <div className="settings-fields"><Form.Item name="name" label="提供商名称" rules={[{ required: true, whitespace: true, max: 100 }]}><Input maxLength={100} /></Form.Item><Form.Item name="logo_url" label="Logo 地址" rules={[urlRule]}><Input /></Form.Item></div>
        <Form.Item name="description" label="提供商简介"><Input.TextArea maxLength={2000} showCount autoSize={{ minRows: 3, maxRows: 6 }} /></Form.Item>
        <div className="settings-fields"><Form.Item name="website_url" label="官网链接" rules={[urlRule]}><Input /></Form.Item><Form.Item name="registration_url" label="注册跳转链接" rules={[urlRule]} extra="可包含邀请码或推广参数"><Input /></Form.Item></div>
        <Form.Item name="base_url" label="API Base URL" rules={[{ required: true }, urlRule]} extra="填写完整 API 根地址，例如 https://api.example.com/v1"><Input /></Form.Item>
        <div className="settings-fields"><Form.Item name="default_model" label="默认模型"><Input maxLength={200} /></Form.Item><Form.Item name="use_responses_api" label="接口模式"><Radio.Group options={[{ label: 'Chat Completions', value: false }, { label: 'Responses', value: true }]} /></Form.Item></div>
        <Form.Item name="recommended_models" label="推荐模型" extra="每行一个，也可使用逗号分隔；用户仍可获取或输入其他模型"><Input.TextArea autoSize={{ minRows: 3, maxRows: 6 }} /></Form.Item>
        <div className="settings-fields"><Form.Item name="sort_order" label="排序值" extra="数值越小越靠前"><InputNumber min={-1000000} max={1000000} precision={0} /></Form.Item><Form.Item name="is_active" label="启用展示与调用" valuePropName="checked"><Switch /></Form.Item></div>
        <Button icon={<EyeOutlined aria-hidden />} onClick={() => setPreview(payload(values))}>预览展示效果</Button>
      </Form>
    </Modal>
    <Modal title="提供商展示预览" open={!!preview} onCancel={() => setPreview(null)} footer={<Button onClick={() => setPreview(null)}>关闭预览</Button>} modalRender={modalFocus}>{preview && <div className="managed-provider-card"><ProviderIdentity provider={preview} /><p className="managed-provider-description">{preview.description || '提供商简介'}</p><ProviderLinks provider={preview} /></div>}</Modal>
  </AdminPage>;
}

export default function AdminAIProviders({ data }: { data: ApiData }) {
  return data.user?.is_admin ? <ProviderManagement data={data} /> : <Result status="403" title="需要管理员权限" />;
}
