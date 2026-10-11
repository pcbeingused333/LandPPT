import { useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Card, Descriptions, Empty, Form, Input, InputNumber, Space, Table, Tabs, Tag } from 'antd';
import { CopyOutlined, DeleteOutlined, ReloadOutlined } from '@ant-design/icons';
import { request, type ApiData } from '../api';
import { modalFocus } from '../components/modal-focus';
import { CreditActions } from '../components/credit-actions';
import { copyText, formatTime, postForm } from '../forms';

function ApiKeys() {
  const { message, modal } = App.useApp();
  const [keys, setKeys] = useState<ApiData[]>([]);
  const [result, setResult] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [pending, setPending] = useState(false);
  const locked = useRef(false);
  const confirming = useRef(false);
  const controller = useRef<AbortController | null>(null);
  const [form] = Form.useForm();
  async function refresh() {
    controller.current?.abort(); const next = new AbortController(); controller.current = next;
    setLoading(true); setError('');
    try { const data = await request('/api/auth/api-keys?include_inactive=true', 'GET', undefined, next.signal); if (!next.signal.aborted) setKeys(data.api_keys || []); }
    catch (error) { if (!next.signal.aborted) setError((error as Error).message); }
    finally { if (!next.signal.aborted) setLoading(false); }
  }
  useEffect(() => { refresh(); return () => controller.current?.abort(); }, []);
  async function create(values: ApiData) {
    if (locked.current) return;
    locked.current = true; setPending(true); setError('');
    try {
      const payload: ApiData = { name: values.name.trim() };
      if (values.api_key?.trim()) payload.api_key = values.api_key.trim();
      if (values.expires_in_days != null) payload.expires_in_days = values.expires_in_days;
      const data = await request('/api/auth/api-keys', 'POST', payload);
      setResult(data.api_key || ''); form.setFieldValue('api_key', '');
      message.success(data.rotated ? 'API Key 轮换成功，请立即保存' : 'API Key 创建成功，请立即保存'); await refresh();
    } catch (error) { setError((error as Error).message); }
    finally { locked.current = false; setPending(false); }
  }
  function remove(key: ApiData) {
    if (confirming.current || locked.current) return;
    confirming.current = true;
    modal.confirm({ title: '删除 API Key', content: `确定删除“${key.name}”吗？删除后不能恢复。`, modalRender: modalFocus, okText: '删除', cancelText: '取消', okButtonProps: { danger: true }, afterClose: () => { confirming.current = false; }, onOk: async () => {
      if (locked.current) throw new Error('请等待当前操作完成');
      locked.current = true; setPending(true);
      try { await request(`/api/auth/api-keys/${Number(key.id)}`, 'DELETE'); message.success('API Key 已删除'); await refresh(); }
      catch (error) { message.error((error as Error).message); throw error; }
      finally { locked.current = false; setPending(false); }
    } });
  }
  const status = (key: ApiData) => <Tag color={key.is_active ? 'success' : 'default'}>{key.is_active ? '可用' : '已禁用'}</Tag>;
  const removeButton = (key: ApiData) => <Button danger type="text" disabled={pending || !Number.isFinite(Number(key.id))} aria-label={`删除 ${key.name}`} icon={<DeleteOutlined aria-hidden />} onClick={() => remove(key)} />;
  return <div className="account-stack">
    {error && <Alert type="error" showIcon title={error} className="page-error" />}
    <Form form={form} layout="vertical" requiredMark={false} disabled={pending} onFinish={create}>
      <div className="settings-fields"><Form.Item name="name" label="Key 名称" rules={[{ required: true, whitespace: true, message: 'Key 名称不能为空' }, { max: 100, message: '名称最多 100 个字符' }]}><Input maxLength={100} placeholder="例如：生产环境" /></Form.Item>
        <Form.Item name="api_key" label="自定义 Key（可选）" extra="留空自动生成；填写时至少 16 位。" rules={[{ validator: (_, value) => !value?.trim() || (value.trim().length >= 16 && value.trim().length <= 512) ? Promise.resolve() : Promise.reject(new Error('自定义 Key 长度需为 16–512 位')) }]}><Input.Password maxLength={512} autoComplete="new-password" /></Form.Item>
        <Form.Item name="expires_in_days" label="过期天数（可选）" rules={[{ type: 'number', min: 1, max: 3650, message: '过期天数需为 1–3650 的整数' }, { validator: (_, value) => value == null || Number.isInteger(value) ? Promise.resolve() : Promise.reject(new Error('请输入整数天数')) }]}><InputNumber min={1} max={3650} precision={0} placeholder="例如：30" /></Form.Item></div>
      <Space wrap><Button type="primary" htmlType="submit" loading={pending}>创建 / 轮换</Button><Button disabled={pending} loading={loading} icon={<ReloadOutlined aria-hidden />} onClick={refresh}>刷新列表</Button></Space>
    </Form>
    {result && <Alert type="success" title="本次生成的 API Key（仅展示一次）" description={<div className="api-key-result"><code>{result}</code><Button icon={<CopyOutlined aria-hidden />} onClick={async () => { try { await copyText(result); message.success('API Key 已复制'); } catch (error) { message.error((error as Error).message); } }}>复制 Key</Button></div>} />}
    <div className="account-table"><Table<ApiData> size="small" loading={loading} rowKey="id" dataSource={keys} pagination={false} scroll={{ x: 760 }} locale={{ emptyText: <Empty description="暂无 API Key" /> }} columns={[
      { title: '名称', dataIndex: 'name', width: 150 }, { title: '前缀', render: (_, key) => <code>{key.key_preview || key.key_prefix || '—'}</code>, width: 140 }, { title: '状态', render: (_, key) => status(key), width: 100 },
      ...[['创建时间', 'created_at'], ['最近使用', 'last_used_at'], ['过期时间', 'expires_at']].map(([title, field]) => ({ title, render: (_: unknown, key: ApiData) => formatTime(key[field]), width: 150 })), { title: '操作', render: (_, key) => removeButton(key), width: 64 },
    ]} /></div>
    <div className="account-mobile-list">{keys.length ? keys.map(key => <Card size="small" key={key.id} title={key.name} extra={removeButton(key)}><Space>{status(key)}<code>{key.key_preview || key.key_prefix || '—'}</code></Space><Descriptions size="small" column={1} items={[
      { key: 'created', label: '创建时间', children: formatTime(key.created_at) }, { key: 'used', label: '最近使用', children: formatTime(key.last_used_at) }, { key: 'expires', label: '过期时间', children: formatTime(key.expires_at) },
    ]} /></Card>) : <Empty description="暂无 API Key" />}</div>
  </div>;
}

export default function Profile({ data }: { data: ApiData }) {
  const user = data.profile;
  const allowed = ['overview', ...(data.creditsEnabled ? ['credits'] : []), 'security', 'apikeys'];
  const initial = location.hash.slice(1);
  const [active, setActive] = useState(allowed.includes(initial) ? initial : data.error || data.success ? 'security' : 'overview');
  const [balance, setBalance] = useState(Number(user.balance || 0));
  const [sending, setSending] = useState(false);
  const passwordSubmitted = useRef(false);
  const [passwordForm] = Form.useForm();
  useEffect(() => {
    const change = () => { const tab = location.hash.slice(1); if (allowed.includes(tab)) setActive(tab); };
    window.addEventListener('hashchange', change); return () => window.removeEventListener('hashchange', change);
  }, [data.creditsEnabled]);
  const items = [
    { key: 'overview', label: '基本信息', children: <Descriptions column={1} size="small" className="profile-info-list" items={[
      { key: 'username', label: '用户名', children: user.username }, ...(user.email ? [{ key: 'email', label: '邮箱', children: user.email }] : []),
      { key: 'status', label: '账户状态', children: <Tag color={user.active ? 'success' : 'error'}>{user.active ? '活跃' : '已禁用'}</Tag> },
      { key: 'role', label: '权限级别', children: user.admin ? '管理员' : '普通用户' }, { key: 'created', label: '注册时间', children: formatTime(user.created) },
      ...(user.lastLogin ? [{ key: 'login', label: '最后登录', children: formatTime(user.lastLogin) }] : []),
    ]} /> },
    ...(data.creditsEnabled ? [{ key: 'credits', label: '我的积分', children: <div className="account-stack"><div className="account-balance"><div><span className="subtle">当前余额</span><strong>{balance.toLocaleString()} <small>积分</small></strong></div><Button href="/credits">查看积分详情 / 充值</Button></div><CreditActions onBalance={setBalance} /></div> }] : []),
    { key: 'security', label: '修改密码', children: <Form form={passwordForm} layout="vertical" requiredMark={false} disabled={sending} className="account-password-form" onFinish={values => { if (passwordSubmitted.current) return; passwordSubmitted.current = true; setSending(true); postForm('/auth/change-password', values); }}>
      {data.error && <Alert type="error" title={data.error} showIcon className="page-error" />}{data.success && <Alert type="success" title={data.success} showIcon className="page-error" />}
      <Form.Item name="current_password" label="当前密码" rules={[{ required: true, message: '请输入当前密码' }]}><Input.Password autoComplete="current-password" /></Form.Item>
      <Form.Item name="new_password" label="新密码" rules={[{ required: true, message: '请输入新密码' }, { min: 6, message: '密码长度至少 6 位' }]}><Input.Password autoComplete="new-password" /></Form.Item>
      <Form.Item name="confirm_password" label="确认新密码" dependencies={['new_password']} rules={[{ required: true, message: '请再次输入新密码' }, ({ getFieldValue }) => ({ validator: (_, value) => !value || value === getFieldValue('new_password') ? Promise.resolve() : Promise.reject(new Error('两次密码输入不一致')) })]}><Input.Password autoComplete="new-password" /></Form.Item><Button type="primary" htmlType="submit" loading={sending}>修改密码</Button>
    </Form> },
    { key: 'apikeys', label: 'API Key', children: <ApiKeys /> },
  ];
  return <div className="account-page profile-shell"><div className="page-heading"><div><h1>个人资料</h1><p>管理账户信息、安全和访问凭证</p></div>{user.admin && <Button href="/admin">管理后台</Button>}</div>
    <Card size="small"><Tabs className="profile-tabs" activeKey={active} onChange={key => { setActive(key); history.replaceState(null, '', `#${key}`); }} items={items} /></Card>
  </div>;
}
