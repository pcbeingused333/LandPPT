import { useEffect, useRef, useState } from 'react';
import { Alert, Avatar, Button, Card, Empty, Form, Input, InputNumber, Modal, Space, Switch, Table, Tag } from 'antd';
import { DeleteOutlined, EditOutlined } from '@ant-design/icons';
import { request, type ApiData } from '../api';
import { useAdminActions } from '../components/admin-data';
import { modalFocus } from '../components/modal-focus';
import { safeWebURL as safeURL } from '../forms';

export default function Sponsors() {
  const [rows, setRows] = useState<ApiData[]>([]); const [loading, setLoading] = useState(true); const [readError, setReadError] = useState('');
  const reading = useRef<AbortController | null>(null); const [editor, setEditor] = useState<ApiData | null>(null); const [form] = Form.useForm(); const actions = useAdminActions();
  async function load() {
    reading.current?.abort(); const controller = new AbortController(); reading.current = controller; setLoading(true); setReadError('');
    try { const result = await request('/admin/api/sponsors', 'GET', undefined, controller.signal); if (!controller.signal.aborted) setRows(result.items || []); }
    catch (reason) { if (!controller.signal.aborted) setReadError((reason as Error).message); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  }
  useEffect(() => { load(); return () => reading.current?.abort(); }, []);
  function open(row?: ApiData) { actions.clearError(); form.resetFields(); form.setFieldsValue(row ? { ...row, is_active: !!row.is_active } : { is_active: true, sort_order: 0 }); setEditor(row || {}); }
  async function save(values: ApiData) {
    const body: ApiData = { sort_order: values.sort_order ?? 0, is_active: !!values.is_active };
    for (const key of ['nickname', 'avatar_url', 'link_url', 'amount', 'bio', 'note']) body[key] = String(values[key] || '').trim() || (key === 'nickname' ? '' : null);
    try { await actions.run(editor?.id ? `/admin/api/sponsors/${editor.id}` : '/admin/api/sponsors', editor?.id ? 'PUT' : 'POST', body); setEditor(null); actions.message.success('赞助信息已保存'); load(); } catch { /* Keep the dialog and values for retry. */ }
  }
  const status = (row: ApiData) => <Tag color={row.is_active ? 'success' : 'default'}>{row.is_active ? '公开展示' : '已隐藏'}</Tag>;
  const identity = (row: ApiData) => <div className="community-sponsor-identity"><Avatar src={safeURL(row.avatar_url)}>{String(row.nickname).slice(0, 1)}</Avatar><div><strong>{row.nickname}</strong>{row.bio && <p className="subtle">{row.bio}</p>}{safeURL(row.link_url) && <a href={safeURL(row.link_url)} target="_blank" rel="noopener noreferrer">访问主页</a>}</div></div>;
  const controls = (row: ApiData) => <Space size={0} className="admin-row-actions"><Button type="text" aria-label={`编辑 ${row.nickname}`} icon={<EditOutlined aria-hidden />} disabled={actions.pending} onClick={() => open(row)} /><Button type="text" danger aria-label={`删除 ${row.nickname}`} icon={<DeleteOutlined aria-hidden />} disabled={actions.pending} onClick={() => actions.confirm('删除赞助信息', `确定删除“${row.nickname}”吗？此操作无法撤销。`, async () => { await actions.run(`/admin/api/sponsors/${row.id}`, 'DELETE'); actions.message.success('赞助信息已删除'); load(); }, true)} /></Space>;
  return <Card size="small" title="赞助名单" className="community-sponsors">
    <div className="admin-toolbar"><Button type="primary" onClick={() => open()} disabled={actions.pending}>新增赞助</Button><Button onClick={load} disabled={loading}>刷新名单</Button><span className="subtle">共 {rows.length} 位，按排序值展示</span></div>
    {readError && <Alert type="error" title={readError} action={<Button onClick={load}>重试</Button>} className="page-error" />}{actions.error && !editor && <Alert type="error" title={actions.error} className="page-error" />}
    <div className="account-table"><Table<ApiData> size="small" rowKey="id" loading={loading} dataSource={rows} pagination={false} scroll={{ x: 860 }} locale={{ emptyText: <Empty description="暂无赞助信息" /> }} columns={[
      { title: '赞助者', width: 270, render: (_, row) => identity(row) }, { title: '金额', width: 100, render: (_, row) => row.amount || '—' }, { title: '排序', width: 80, dataIndex: 'sort_order' }, { title: '展示状态', width: 130, render: (_, row) => status(row) }, { title: '备注', width: 180, render: (_, row) => row.note || '—' }, { title: '操作', width: 100, fixed: 'right', render: (_, row) => controls(row) },
    ]} /></div>
    <div className="account-mobile-list">{loading && <p role="status">正在加载…</p>}{rows.length ? rows.map(row => <Card size="small" key={row.id}>{identity(row)}<p>{row.amount || '未填写金额'} · 排序 {row.sort_order}</p>{status(row)}{row.note && <p className="subtle">{row.note}</p>}{controls(row)}</Card>) : !loading && <Empty description="暂无赞助信息" />}</div>
    <Modal title={editor?.id ? '编辑赞助' : '新增赞助'} open={!!editor} width={620} onCancel={() => { if (!actions.pending) setEditor(null); }} onOk={() => form.submit()} okText="保存赞助" cancelText="取消" confirmLoading={actions.pending} cancelButtonProps={{ disabled: actions.pending }} closable={!actions.pending} maskClosable={!actions.pending} keyboard={!actions.pending} modalRender={modalFocus}>
      {actions.error && <Alert type="error" title={actions.error} className="page-error" />}
      <Form form={form} name="communitySponsor" layout="vertical" requiredMark={false} disabled={actions.pending} onFinish={save}>
        <Form.Item name="nickname" label="昵称" rules={[{ required: true, whitespace: true, message: '请填写昵称' }]}><Input /></Form.Item>
        <div className="settings-fields"><Form.Item name="avatar_url" label="头像 URL"><Input /></Form.Item><Form.Item name="link_url" label="主页 URL"><Input /></Form.Item><Form.Item name="amount" label="赞助金额" extra="支持金额文字，例如 ¥100"><Input /></Form.Item><Form.Item name="sort_order" label="排序值"><InputNumber precision={0} /></Form.Item></div>
        <Form.Item name="bio" label="简介"><Input.TextArea rows={2} /></Form.Item><Form.Item name="note" label="备注"><Input.TextArea rows={2} /></Form.Item><Form.Item name="is_active" label="公开展示" valuePropName="checked"><Switch /></Form.Item>
      </Form>
    </Modal>
  </Card>;
}
