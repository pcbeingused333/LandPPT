import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Card, Form, Input, InputNumber, Result, Select, Space, Tabs, Tag } from 'antd';
import { CopyOutlined, DeleteOutlined } from '@ant-design/icons';
import { type ApiData } from '../api';
import { copyText, formatTime } from '../forms';
import { AdminPage } from '../components/admin';
import { AdminCollection, useAdminActions, useAdminList } from '../components/admin-data';

function CodesList({ active }: { active: boolean }) {
  const [filters, setFilters] = useState<ApiData>({ page_size: 20, is_used: '', search: '', created_by: null });
  const [search, setSearch] = useState(''); const [creator, setCreator] = useState<number | null>(null);
  const state = useAdminList('/admin/api/redemption-codes', 'codes', filters); const actions = useAdminActions();
  const seen = useRef(false);
  useEffect(() => { if (seen.current && active) state.refresh(); seen.current = true; }, [active]);
  const apply = () => setFilters(previous => ({ ...previous, search: search.trim(), created_by: creator }));
  async function copy(code: string) { try { await copyText(code); actions.message.success('兑换码已复制'); } catch (reason) { actions.message.error((reason as Error).message); } }
  function status(code: ApiData) { const expired = code.expires_at && Number(code.expires_at) * 1000 < Date.now(); return <Tag color={code.is_used ? 'default' : expired ? 'warning' : 'success'}>{code.is_used ? '已使用' : expired ? '已过期' : '可用'}</Tag>; }
  const controls = (code: ApiData) => <Space size={0} className="admin-row-actions"><Button type="text" icon={<CopyOutlined aria-hidden />} aria-label={`复制 ${code.code}`} onClick={() => copy(code.code)} />{!code.is_used && <Button type="text" danger disabled={actions.pending} aria-label={`删除 ${code.code}`} icon={<DeleteOutlined aria-hidden />} onClick={() => actions.confirm('删除兑换码', `确定删除“${code.code}”吗？`, async () => { await actions.run(`/admin/api/redemption-codes/${code.id}`, 'DELETE'); actions.message.success('兑换码已删除'); state.refresh(); }, true)} />}</Space>;
  const query = new URLSearchParams(Object.entries({ is_used: filters.is_used, search: search.trim(), created_by: creator }).filter(([, value]) => value !== '' && value != null).map(([name, value]) => [name, String(value)]));
  return <>
    <div className="admin-toolbar"><Input.Search aria-label="搜索兑换码" placeholder="搜索兑换码或备注" value={search} allowClear onChange={event => setSearch(event.target.value)} onSearch={apply} /><InputNumber aria-label="创建人 ID" placeholder="创建人 ID" min={1} precision={0} value={creator} onChange={value => { setCreator(value); setFilters(previous => ({ ...previous, created_by: value })); }} />
      <Select aria-label="兑换码状态" value={filters.is_used} options={[{ value: '', label: '全部状态' }, { value: 'false', label: '未使用' }, { value: 'true', label: '已使用' }]} onChange={is_used => setFilters(previous => ({ ...previous, is_used }))} /><Button href={'/admin/api/redemption-codes/export?' + query}>导出 CSV</Button>
    </div>
    <div className="admin-toolbar admin-sortbar"><Select aria-label="每页数量" value={filters.page_size} options={[20, 50, 100].map(value => ({ value, label: `${value} / 页` }))} onChange={page_size => setFilters(previous => ({ ...previous, page_size }))} /><Button disabled={state.loading} onClick={state.refresh}>刷新列表</Button></div>
    {actions.error && <Alert type="error" title={actions.error} className="page-error" />}
    <AdminCollection state={state} pageSize={filters.page_size} columns={[
      { title: '兑换码', width: 210, render: (_, code) => <code className="admin-code">{code.code}</code> }, { title: '积分', dataIndex: 'credits_amount', width: 90 }, { title: '状态', width: 110, render: (_, code) => status(code) }, { title: '使用者', width: 90, render: (_, code) => code.used_by ?? '—' },
      { title: '创建时间', width: 185, render: (_, code) => formatTime(code.created_at) }, { title: '有效期', width: 185, render: (_, code) => code.expires_at ? formatTime(code.expires_at) : '永久' }, { title: '操作', width: 100, fixed: 'right', render: (_, code) => controls(code) },
    ]} card={code => <><div className="credit-record-heading"><code className="admin-code">{code.code}</code>{status(code)}</div><p>{code.credits_amount} 积分 · 使用者 {code.used_by ?? '—'}</p><p className="subtle">创建 {formatTime(code.created_at)}<br />有效期 {code.expires_at ? formatTime(code.expires_at) : '永久'}</p>{controls(code)}</>} />
  </>;
}

function Credits({ data }: { data: ApiData }) {
  const [form] = Form.useForm(); const actions = useAdminActions(); const [codes, setCodes] = useState<ApiData[]>([]); const [active, setActive] = useState('generate');
  return <AdminPage title="积分管理" description="生成、查询和导出兑换码" credits={data.creditsEnabled}>
    <Tabs activeKey={active} onChange={setActive} items={[
      { key: 'generate', label: '生成兑换码', children: <div className="settings-stack">
        {actions.error && <Alert type="error" title={actions.error} />}
        <Card size="small" title="批量生成"><Form form={form} name="redemption" layout="vertical" requiredMark={false} disabled={actions.pending} initialValues={{ count: 10, credits_amount: 100 }} onFinish={async values => {
          const body: ApiData = { count: values.count, credits_amount: values.credits_amount };
          if (values.expires_in_days != null) body.expires_in_days = values.expires_in_days;
          if (values.description) body.description = values.description;
          try { const result = await actions.run('/admin/api/redemption-codes', 'POST', body); setCodes(result.codes || []); actions.message.success(`成功生成 ${result.codes?.length || 0} 个兑换码`); } catch { /* Preserve inputs and previous result. */ }
        }}><div className="settings-fields"><Form.Item name="count" label="生成数量" rules={[{ required: true, message: '请输入数量' }, { type: 'number', min: 1, max: 100, message: '数量需为 1–100' }]}><InputNumber min={1} max={100} precision={0} /></Form.Item><Form.Item name="credits_amount" label="每个兑换码积分" rules={[{ required: true, message: '请输入积分' }, { type: 'number', min: 1, message: '积分至少为 1' }]}><InputNumber min={1} precision={0} /></Form.Item><Form.Item name="expires_in_days" label="有效天数（可选）" extra="留空永久有效" rules={[{ type: 'number', min: 1, message: '天数至少为 1' }]}><InputNumber min={1} precision={0} /></Form.Item><Form.Item name="description" label="备注（可选）"><Input /></Form.Item></div><Button htmlType="submit" type="primary" loading={actions.pending}>立即生成</Button></Form></Card>
        {codes.length > 0 && <Card size="small" title={`本次生成 ${codes.length} 个兑换码`} extra={<Button onClick={async () => { try { await copyText(codes.map(code => code.code).join('\n')); actions.message.success('已复制全部兑换码'); } catch (reason) { actions.message.error((reason as Error).message); } }}>复制全部</Button>}><div className="admin-generated-codes">{codes.map(code => <div key={code.code}><code>{code.code}</code><Button type="text" aria-label={`复制 ${code.code}`} icon={<CopyOutlined aria-hidden />} onClick={async () => { try { await copyText(code.code); actions.message.success('兑换码已复制'); } catch (reason) { actions.message.error((reason as Error).message); } }} /></div>)}</div></Card>}
      </div> },
      { key: 'list', label: '兑换码列表', children: <CodesList active={active === 'list'} /> },
    ]} />
  </AdminPage>;
}

export default function AdminCredits({ data }: { data: ApiData }) {
  return !data.user?.is_admin ? <Result status="403" title="需要管理员权限" /> : !data.creditsEnabled ? <Result status="403" title="积分系统未启用" /> : <Credits data={data} />;
}
