import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, App, Avatar, Button, Card, Checkbox, Empty, Form, Input, Modal, Radio, Space, Tag } from 'antd';
import { ApiOutlined, ArrowRightOutlined, ReloadOutlined } from '@ant-design/icons';
import { request, type ApiData } from '../api';
import { modalFocus } from './modal-focus';
import { ModelPicker } from './model-picker';
import type { Field } from '../settings-schema';
import './managed-providers.css';

export type ManagedProvider = ApiData & { id: string; provider: string; name: string; is_active: boolean; base_url: string; recommended_models: string[] };

export function useManagedProviders() {
  const [providers, setProviders] = useState<ManagedProvider[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const active = useRef<AbortController | null>(null);
  const reload = useCallback(async () => {
    active.current?.abort(); const controller = new AbortController(); active.current = controller;
    setLoading(true); setError('');
    try { const result = await request('/api/managed-providers', 'GET', undefined, controller.signal); if (!controller.signal.aborted) setProviders(result.providers || []); }
    catch (reason) { if (!controller.signal.aborted) setError((reason as Error).message); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  }, []);
  useEffect(() => { reload(); return () => active.current?.abort(); }, [reload]);
  return { providers, error, loading, reload };
}

export function ProviderIdentity({ provider }: { provider: ApiData }) {
  return <div className="managed-provider-identity"><Avatar shape="square" size={40} src={provider.logo_url || undefined}>{String(provider.name || 'AI').slice(0, 2)}</Avatar><div><strong>{provider.name}</strong><span className="subtle">OpenAI 兼容{provider.use_responses_api ? ' · Responses' : ''}</span></div></div>;
}

export function ProviderLinks({ provider }: { provider: ApiData }) {
  const safe = (value: string) => { try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? value : ''; } catch { return ''; } };
  const website = safe(provider.website_url); const registration = safe(provider.registration_url);
  return <Space wrap>{website && <Button type="link" href={website} target="_blank" rel="noopener noreferrer">访问官网</Button>}{registration && <Button href={registration} target="_blank" rel="noopener noreferrer" icon={<ArrowRightOutlined aria-hidden />}>前往注册</Button>}</Space>;
}

export default function ManagedProviders({ catalogue, current, chooseDefault, busy }: {
  catalogue: ReturnType<typeof useManagedProviders>; current: string; chooseDefault: (name: string) => void; busy: boolean;
}) {
  const { message, modal } = App.useApp();
  const [selected, setSelected] = useState<ManagedProvider | null>(null);
  const [key, setKey] = useState(''); const [model, setModel] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [options, setOptions] = useState<Field['options'] | undefined>();
  const [pending, setPending] = useState(''); const [error, setError] = useState('');
  const lock = useRef(false); const active = useRef<AbortController | null>(null);
  useEffect(() => () => active.current?.abort(), []);
  function open(provider: ManagedProvider) {
    setSelected(provider); setKey(''); setModel(provider.model || provider.default_model || '');
    setOptions(undefined); setConfirmed(!provider.requires_confirmation); setError('');
  }
  async function run(kind: string) {
    if (!selected || lock.current) return;
    if (!confirmed) { setError('请先确认当前 API 地址'); return; }
    lock.current = true; setPending(kind); setError('');
    const controller = new AbortController(); active.current = controller;
    try {
      const body = { api_key: key.trim() || null, model: model.trim(), confirmed_base_url: selected.base_url };
      const result = await request(`/api/managed-providers/${selected.id}/${kind === 'save' ? 'config' : kind}`, kind === 'save' ? 'PUT' : 'POST', body, controller.signal);
      if (controller.signal.aborted) return;
      if (kind === 'models') { setOptions((result.models || []).map((value: string) => ({ label: value, value }))); message.success(`已获取 ${result.models?.length || 0} 个模型`); }
      else if (kind === 'test') message.success('连接成功');
      else { setKey(''); setSelected(null); await catalogue.reload(); message.success('提供商配置已保存'); }
    } catch (reason) { if (!controller.signal.aborted) setError((reason as Error).message); }
    finally { lock.current = false; if (!controller.signal.aborted) setPending(''); }
  }
  function clear(provider: ManagedProvider) {
    modal.confirm({ title: `清除 ${provider.name} 的个人配置？`, content: '清除后需要重新填写 API Key。使用此提供商的任务会提示重新配置。', okText: '清除配置', cancelText: '取消', onOk: async () => {
      if (lock.current) return Promise.reject();
      lock.current = true; setPending('clear');
      try { await request(`/api/managed-providers/${provider.id}/config`, 'DELETE'); await catalogue.reload(); }
      finally { lock.current = false; setPending(''); }
    } });
  }
  const field: Field = { name: 'managed_provider_model', label: '模型', kind: 'text', help: '', placeholder: '输入模型名称或获取列表', value: '', required: false, section: '', dependencies: [], options: (selected?.recommended_models || []).map(value => ({ label: value, value })) };
  return <Card size="small" className="managed-providers" title={<span className="config-card-title"><ApiOutlined aria-hidden />AI 提供商</span>} extra={<Button type="text" aria-label="刷新 AI 提供商" icon={<ReloadOutlined aria-hidden />} loading={catalogue.loading} disabled={!!pending} onClick={catalogue.reload} />}>
    {catalogue.error && <Alert type="error" title="AI 提供商加载失败" description={catalogue.error} />}
    {!catalogue.loading && !catalogue.error && !catalogue.providers.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂未添加 AI 提供商" />}
    <div className="managed-provider-grid">{catalogue.providers.map(provider => <article className="managed-provider-card" key={provider.id}>
      <div className="managed-provider-heading"><ProviderIdentity provider={provider} /><Tag>{!provider.is_active ? '已停用' : provider.requires_confirmation ? '地址待确认' : provider.configured ? '已配置' : '未配置'}</Tag></div>
      <p className="managed-provider-description">{provider.description || '配置自己的 API Key，使用此服务生成演示文稿。'}</p>
      <ProviderLinks provider={provider} />
      <div className="managed-provider-actions"><Radio aria-label={`设 ${provider.name} 为默认`} checked={current === provider.provider} disabled={busy || !!pending || !provider.configured} onChange={() => chooseDefault(provider.provider)}>{current === provider.provider ? '当前默认' : '设为默认'}</Radio><Space wrap>{provider.has_api_key && <Button type="text" disabled={!!pending || busy} onClick={() => clear(provider)}>清除配置</Button>}<Button disabled={!provider.is_active || !!pending || busy} onClick={() => open(provider)}>配置使用</Button></Space></div>
    </article>)}</div>
    <Modal title={selected ? `配置 ${selected.name}` : '配置 AI 提供商'} open={!!selected} onCancel={() => { if (!pending) { setSelected(null); setKey(''); } }} closable={!pending} maskClosable={false} keyboard={!pending} destroyOnHidden modalRender={modalFocus} footer={<Space wrap><Button disabled={!!pending} onClick={() => { setSelected(null); setKey(''); }}>取消</Button><Button loading={pending === 'test'} disabled={!!pending && pending !== 'test'} onClick={() => run('test')}>测试连接</Button><Button type="primary" loading={pending === 'save'} disabled={!!pending && pending !== 'save'} onClick={() => run('save')}>保存配置</Button></Space>}>
      {selected && <Form layout="vertical" disabled={!!pending}>
        <ProviderIdentity provider={selected} />
        {error && <Alert className="page-error" type="error" title={error} />}
        <Form.Item label="API 地址" htmlFor="managed-base-url"><Input id="managed-base-url" value={selected.base_url} readOnly /></Form.Item>
        {selected.requires_confirmation && <Form.Item><Checkbox checked={confirmed} onChange={event => setConfirmed(event.target.checked)}>我已确认新的 API 地址，允许向此服务发送密钥和生成内容</Checkbox></Form.Item>}
        <Form.Item label="API Key" htmlFor="managed-api-key" extra={selected.has_api_key ? '已保存密钥，留空保留；填写新密钥可替换。' : '请填写你在此服务申请的 API Key。'}><Input.Password id="managed-api-key" value={key} onChange={event => setKey(event.target.value)} autoComplete="new-password" /></Form.Item>
        <Form.Item label="模型" htmlFor="field-managed_provider_model"><div className="model-control"><ModelPicker field={field} value={model} options={options || field.options} fetched={options} disabled={!!pending} change={(_, value) => setModel(String(value))} /><Button aria-label="获取提供商模型列表" icon={<ReloadOutlined aria-hidden />} loading={pending === 'models'} disabled={!!pending && pending !== 'models'} onClick={() => run('models')} /></div></Form.Item>
        <p className="subtle">调用费用由此服务按你的账号计费。</p>
      </Form>}
    </Modal>
  </Card>;
}
