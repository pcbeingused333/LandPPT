import { useState } from 'react';
import { Alert, Button, Card, Form, Input, InputNumber, Select, Space, Tag } from 'antd';
import { CopyOutlined, DeleteOutlined } from '@ant-design/icons';
import type { ApiData } from '../api';
import { copyText, formatTime } from '../forms';
import { AdminCollection, useAdminActions, useAdminList } from '../components/admin-data';

const defaults = { count: 5, channel: 'universal', credits_amount: 0, max_uses: 1 };
const channels = [{ value: 'universal', label: '通用渠道' }, { value: 'mail', label: 'Mail' }, { value: 'github', label: 'GitHub' }, { value: 'linuxdo', label: 'LinuxDo' }];

export default function Invites() {
  const [form] = Form.useForm(); const [pageSize, setPageSize] = useState(20); const [created, setCreated] = useState<ApiData[]>([]);
  const state = useAdminList('/admin/api/invite-codes', 'items', { page_size: pageSize }); const actions = useAdminActions();
  async function copy(text: string) { try { await copyText(text); actions.message.success('邀请码已复制'); } catch (reason) { actions.message.error((reason as Error).message); } }
  async function create(values: ApiData) {
    const body = { count: values.count, channel: values.channel, credits_amount: values.credits_amount, max_uses: values.max_uses, description: String(values.description || '').trim() || null, expires_in_days: values.expires_in_days ?? null };
    try { const result = await actions.run('/admin/api/invite-codes', 'POST', body); setCreated(result.items || []); form.resetFields(); actions.message.success(`已生成 ${result.items?.length || 0} 个邀请码`); state.changePage(1); } catch { /* Keep inputs and the previous result for retry. */ }
  }
  const channel = (row: ApiData) => channels.find(item => item.value === row.channel)?.label || row.channel;
  const status = (row: ApiData) => {
    const expired = row.expires_at && Number(row.expires_at) * 1000 < Date.now(); const exhausted = Number(row.used_count || 0) >= Number(row.max_uses);
    return <Tag color={!row.is_active ? 'default' : expired || exhausted ? 'warning' : 'success'}>{!row.is_active ? '停用' : expired ? '已过期' : exhausted ? '已用完' : '可用'}</Tag>;
  };
  const controls = (row: ApiData) => <Space wrap size={0} className="admin-row-actions">
    <Button type="text" icon={<CopyOutlined aria-hidden />} aria-label={`复制 ${row.code}`} onClick={() => copy(row.code)} />
    <Button type="text" disabled={actions.pending} aria-label={`${row.is_active ? '停用' : '启用'} ${row.code}`} onClick={async () => { try { await actions.run(`/admin/api/invite-codes/${row.id}`, 'PATCH', { is_active: !row.is_active }); actions.message.success('邀请码状态已更新'); state.refresh(); } catch { /* Show the error and retain the row. */ } }}>{row.is_active ? '停用' : '启用'}</Button>
    <Button type="text" danger icon={<DeleteOutlined aria-hidden />} disabled={actions.pending || Number(row.used_count) > 0} title={Number(row.used_count) > 0 ? '已使用的邀请码不能删除' : undefined} aria-label={`删除 ${row.code}`} onClick={() => actions.confirm('删除邀请码', `确定删除“${row.code}”吗？此操作无法撤销。`, async () => { await actions.run(`/admin/api/invite-codes/${row.id}`, 'DELETE'); actions.message.success('邀请码已删除'); state.refresh(); }, true)} />
  </Space>;
  return <div className="settings-stack community-invites">
    {actions.error && <Alert type="error" title={actions.error} />}
    <Card size="small" title="批量生成邀请码"><Form form={form} name="communityInvites" layout="vertical" requiredMark={false} initialValues={defaults} disabled={actions.pending} onFinish={create}>
      <div className="settings-fields">
        <Form.Item name="count" label="生成数量" rules={[{ required: true, type: 'number', min: 1, max: 100, message: '请输入 1–100 的数量' }]}><InputNumber min={1} max={100} precision={0} /></Form.Item>
        <Form.Item name="channel" label="注册渠道"><Select options={channels} /></Form.Item>
        <Form.Item name="credits_amount" label="赠送积分" rules={[{ required: true, type: 'number', min: 0, message: '积分不能为负数' }]}><InputNumber min={0} precision={0} /></Form.Item>
        <Form.Item name="max_uses" label="最大使用次数" rules={[{ required: true, type: 'number', min: 1, message: '使用次数至少为 1' }]}><InputNumber min={1} precision={0} /></Form.Item>
        <Form.Item name="expires_in_days" label="有效天数（可选）" extra="留空永久有效" rules={[{ type: 'number', min: 1, message: '有效天数至少为 1' }]}><InputNumber min={1} precision={0} /></Form.Item>
        <Form.Item name="description" label="备注（可选）"><Input /></Form.Item>
      </div><Button htmlType="submit" type="primary" loading={actions.pending}>生成邀请码</Button>
    </Form></Card>
    {created.length > 0 && <Card size="small" title={`本次生成 ${created.length} 个邀请码`} extra={<Button onClick={() => copy(created.map(row => row.code).join('\n'))}>复制全部</Button>}><div className="admin-generated-codes">{created.map(row => <div key={row.code}><code>{row.code}</code><Button type="text" icon={<CopyOutlined aria-hidden />} aria-label={`复制新邀请码 ${row.code}`} onClick={() => copy(row.code)} /></div>)}</div></Card>}
    <Card size="small" title="邀请码列表"><div className="admin-toolbar"><Select aria-label="每页数量" value={pageSize} options={[20, 50, 100].map(value => ({ value, label: `${value} / 页` }))} onChange={setPageSize} /><Button disabled={state.loading} onClick={state.refresh}>刷新列表</Button><Button href="/admin/api/invite-codes/export">导出 CSV</Button></div>
      <AdminCollection state={state} pageSize={pageSize} columns={[
        { title: '邀请码', width: 210, render: (_, row) => <div><code className="admin-code">{row.code}</code>{row.description && <p className="subtle">{row.description}</p>}</div> }, { title: '渠道', width: 110, render: (_, row) => channel(row) }, { title: '积分', width: 80, dataIndex: 'credits_amount' },
        { title: '已用 / 上限', width: 115, render: (_, row) => `${row.used_count ?? 0} / ${row.max_uses}` }, { title: '有效期', width: 180, render: (_, row) => row.expires_at ? formatTime(row.expires_at) : '永久' }, { title: '状态', width: 100, render: (_, row) => status(row) }, { title: '操作', width: 150, fixed: 'right', render: (_, row) => controls(row) },
      ]} card={row => <><div className="credit-record-heading"><code className="admin-code">{row.code}</code>{status(row)}</div><p>{channel(row)} · {row.credits_amount} 积分 · 已用 {row.used_count ?? 0} / {row.max_uses}</p><p className="subtle">有效期 {row.expires_at ? formatTime(row.expires_at) : '永久'}{row.description && <><br />{row.description}</>}</p>{controls(row)}</>} />
    </Card>
  </div>;
}
