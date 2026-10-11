import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Descriptions, Form, Input, InputNumber, Modal, Result, Select, Space, Tag } from 'antd';
import { EditOutlined, KeyOutlined, DollarOutlined, StopOutlined, CheckOutlined } from '@ant-design/icons';
import { request, type ApiData } from '../api';
import { copyText, formatTime } from '../forms';
import { modalFocus } from '../components/modal-focus';
import { AdminPage } from '../components/admin';
import { AdminCollection, useAdminActions, useAdminList } from '../components/admin-data';

const sortFields = [['created_at', '注册时间'], ['id', 'ID'], ['username', '用户名'], ['email', '邮箱'], ['is_active', '状态'], ['is_admin', '角色'], ['credits_balance', '积分余额'], ['projects_count', '项目数'], ['credits_consumed_total', '累计消耗'], ['last_active_at', '最近活跃']];

function Users({ data }: { data: ApiData }) {
  const [filters, setFilters] = useState<ApiData>({ page_size: 20, is_active: '', is_admin: '', search: '', sort_by: 'created_at', sort_dir: 'desc' });
  const state = useAdminList('/admin/api/users', 'users', filters); const actions = useAdminActions();
  const [editor, setEditor] = useState<ApiData | null>(null); const [detail, setDetail] = useState<ApiData | null>(null); const [detailError, setDetailError] = useState(''); const [detailLoading, setDetailLoading] = useState(false);
  const detailRequest = useRef<AbortController | null>(null);
  const [creditUser, setCreditUser] = useState<ApiData | null>(null); const [secret, setSecret] = useState('');
  const [form] = Form.useForm(); const [creditForm] = Form.useForm();
  useEffect(() => () => detailRequest.current?.abort(), []);
  function create() { detailRequest.current?.abort(); setDetail(null); setDetailError(''); setDetailLoading(false); actions.clearError(); form.resetFields(); setEditor({ mode: 'create' }); }
  async function edit(user: ApiData) {
    detailRequest.current?.abort(); const controller = new AbortController(); detailRequest.current = controller;
    setEditor({ mode: 'edit', id: user.id }); setDetail(null); setDetailError(''); setDetailLoading(true); actions.clearError();
    try {
      const result = await request(`/admin/api/users/${user.id}`, 'GET', undefined, controller.signal);
      if (!controller.signal.aborted) { setDetail(result.user); form.setFieldsValue({ username: result.user.username, email: result.user.email || '', is_admin: !!result.user.is_admin }); }
    } catch (reason) { if (!controller.signal.aborted) setDetailError((reason as Error).message); }
    finally { if (!controller.signal.aborted) setDetailLoading(false); }
  }
  function close() { if (actions.pending) return; detailRequest.current?.abort(); setEditor(null); }
  async function save(values: ApiData) {
    const isEdit = editor?.mode === 'edit';
    const body: ApiData = { email: values.email || null, is_admin: !!values.is_admin };
    if (!isEdit) { body.username = values.username; body.password = values.password; if (data.creditsEnabled) body.credits_balance = values.credits_balance ?? 0; }
    try { await actions.run(isEdit ? `/admin/api/users/${editor!.id}` : '/admin/api/users', isEdit ? 'PUT' : 'POST', body); setEditor(null); actions.message.success(isEdit ? '用户已更新' : '用户已创建'); state.refresh(); } catch { /* Keep form values for retry. */ }
  }
  function accountState(user: ApiData) {
    const title = user.is_active ? '停用用户' : '启用用户';
    actions.confirm(title, `确定${user.is_active ? '停用' : '启用'}“${user.username}”吗？`, async () => { await actions.run(`/admin/api/users/${user.id}`, user.is_active ? 'DELETE' : 'PUT', user.is_active ? undefined : { is_active: true }); actions.message.success(title + '成功'); state.refresh(); }, !!user.is_active);
  }
  const controls = (user: ApiData) => <Space wrap size={0} className="admin-row-actions">
    <Button type="text" aria-label={`编辑 ${user.username}`} icon={<EditOutlined aria-hidden />} disabled={actions.pending} onClick={() => edit(user)} />
    {data.creditsEnabled && <Button type="text" aria-label={`调整积分 ${user.username}`} icon={<DollarOutlined aria-hidden />} disabled={actions.pending} onClick={() => { actions.clearError(); creditForm.resetFields(); setCreditUser(user); }} />}
    <Button type="text" aria-label={`重置密码 ${user.username}`} icon={<KeyOutlined aria-hidden />} disabled={actions.pending} onClick={() => actions.confirm('重置用户密码', `确定重置“${user.username}”的密码吗？`, async () => { const result = await actions.run(`/admin/api/users/${user.id}/reset-password`, 'POST'); setSecret(result.temporary_password); }, true)} />
    <Button type="text" danger={!!user.is_active} aria-label={`${user.is_active ? '停用' : '启用'} ${user.username}`} icon={user.is_active ? <StopOutlined aria-hidden /> : <CheckOutlined aria-hidden />} disabled={actions.pending || (user.is_active && user.id === data.adminId)} onClick={() => accountState(user)} />
  </Space>;
  const status = (user: ApiData) => <Space size={0}><Tag color={user.is_active ? 'success' : 'default'}>{user.is_active ? '活跃' : '已停用'}</Tag><Tag>{user.is_admin ? '管理员' : '用户'}</Tag></Space>;
  const metrics = detail?.metrics || {};
  return <AdminPage title="用户管理" description="管理账户、权限与使用情况" credits={data.creditsEnabled}>
    <div className="admin-toolbar"><Input.Search aria-label="搜索用户" placeholder="搜索用户名或邮箱" allowClear onSearch={search => setFilters(previous => ({ ...previous, search: search.trim() }))} />
      <Select aria-label="状态筛选" value={filters.is_active} onChange={is_active => setFilters(previous => ({ ...previous, is_active }))} options={[{ value: '', label: '全部状态' }, { value: 'true', label: '活跃' }, { value: 'false', label: '已停用' }]} />
      <Select aria-label="角色筛选" value={filters.is_admin} onChange={is_admin => setFilters(previous => ({ ...previous, is_admin }))} options={[{ value: '', label: '全部角色' }, { value: 'true', label: '管理员' }, { value: 'false', label: '用户' }]} />
      <Button id="createUserBtn" type="primary" onClick={create} disabled={actions.pending}>新建用户</Button>
    </div>
    <div className="admin-toolbar admin-sortbar"><Select aria-label="排序字段" value={filters.sort_by} onChange={sort_by => setFilters(previous => ({ ...previous, sort_by }))} options={sortFields.filter(([key]) => data.creditsEnabled || key !== 'credits_balance').map(([value, label]) => ({ value, label }))} /><Button onClick={() => setFilters(previous => ({ ...previous, sort_dir: previous.sort_dir === 'desc' ? 'asc' : 'desc' }))}>{filters.sort_dir === 'desc' ? '降序' : '升序'}</Button><Select aria-label="每页数量" value={filters.page_size} options={[20, 50, 100].map(value => ({ value, label: `${value} / 页` }))} onChange={page_size => setFilters(previous => ({ ...previous, page_size }))} /><Button disabled={state.loading} onClick={state.refresh}>刷新</Button></div>
    {actions.error && !editor && !creditUser && <Alert type="error" title={actions.error} className="page-error" />}
    <AdminCollection state={state} pageSize={filters.page_size} columns={[
      { title: '用户', width: 210, render: (_, user) => <div className="admin-user-name"><strong>{user.username}</strong><span className="subtle">ID {user.id} · {user.email || '未填写邮箱'}</span></div> },
      { title: '状态 / 角色', width: 150, render: (_, user) => status(user) },
      ...(data.creditsEnabled ? [{ title: '积分', dataIndex: 'credits_balance', width: 90 }] : []),
      { title: '使用情况', width: 120, render: (_, user) => <div><span>项目 {user.metrics?.projects_count ?? 0}</span><br /><span className="subtle">累计消耗 {user.metrics?.credits_consumed_total ?? 0}</span></div> },
      { title: '最近活跃 / 注册', width: 195, render: (_, user) => <div><span>{formatTime(user.metrics?.last_active_at)}</span><br /><span className="subtle">{formatTime(user.created_at)}</span></div> },
      { title: '操作', width: 155, fixed: 'right', render: (_, user) => controls(user) },
    ]} card={user => <><div className="admin-user-name"><strong>{user.username}</strong><span className="subtle">ID {user.id} · {user.email || '未填写邮箱'}</span></div>{status(user)}<p className="subtle">项目 {user.metrics?.projects_count ?? 0} · 累计消耗 {user.metrics?.credits_consumed_total ?? 0}{data.creditsEnabled && ` · 余额 ${user.credits_balance ?? 0}`}<br />最近活跃 {formatTime(user.metrics?.last_active_at)}<br />注册 {formatTime(user.created_at)}</p>{controls(user)}</>} />
    <Modal title={editor?.mode === 'edit' ? '编辑用户' : '新建用户'} open={!!editor} onCancel={close} onOk={() => form.submit()} okText="保存用户" cancelText="取消" width={620} modalRender={modalFocus} confirmLoading={actions.pending} okButtonProps={{ disabled: detailLoading || (editor?.mode === 'edit' && !detail) }} cancelButtonProps={{ disabled: actions.pending }} closable={!actions.pending} maskClosable={!actions.pending}>
      {detailError && <Alert type="error" title={detailError} action={<Button onClick={() => edit({ id: editor?.id })}>重试</Button>} className="page-error" />}{actions.error && <Alert type="error" title={actions.error} className="page-error" />}
      <Form form={form} name="adminUser" layout="vertical" requiredMark={false} disabled={detailLoading || actions.pending || (editor?.mode === 'edit' && !detail)} initialValues={{ is_admin: false, credits_balance: 100 }} onFinish={save}>
        <Form.Item name="username" label="用户名" htmlFor="userUsername" rules={[{ required: true, whitespace: true, message: '请输入用户名' }]}><Input id="userUsername" disabled={editor?.mode === 'edit' || actions.pending} autoComplete="off" /></Form.Item>
        {editor?.mode !== 'edit' && <Form.Item name="password" label="初始密码" rules={[{ required: true, message: '请输入初始密码' }]}><Input.Password autoComplete="new-password" /></Form.Item>}
        <div className="settings-fields"><Form.Item name="email" label="邮箱" rules={[{ type: 'email', message: '请输入有效邮箱' }]}><Input type="email" /></Form.Item><Form.Item name="is_admin" label="角色"><Select disabled={actions.pending || (editor?.mode === 'edit' && editor?.id === data.adminId)} options={[{ value: false, label: '普通用户' }, { value: true, label: '管理员' }]} /></Form.Item></div>
        {data.creditsEnabled && editor?.mode !== 'edit' && <Form.Item name="credits_balance" label="初始积分" rules={[{ type: 'number', min: 0, message: '积分不能为负数' }]}><InputNumber min={0} precision={0} /></Form.Item>}
      </Form>
      {detail && <Descriptions size="small" column={1} title="用户详情" items={[
        ...[['手机', 'phone'], ['注册渠道', 'registration_channel'], ['OAuth 提供者', 'oauth_provider'], ['注册 IP', 'register_ip'], ['最近登录 IP', 'last_login_ip']].map(([label, field]) => ({ key: field, label, children: detail[field] || '—' })),
        { key: 'login', label: '最近登录', children: formatTime(detail.last_login) }, { key: 'projects', label: '项目数', children: metrics.projects_count ?? 0 }, { key: 'consumed', label: '累计消耗', children: metrics.credits_consumed_total ?? 0 }, { key: 'active', label: '最近活跃', children: formatTime(metrics.last_active_at) }, { key: 'project', label: '最近创建项目', children: formatTime(metrics.last_project_created_at) },
      ]} />}
    </Modal>
    <Modal title={`调整积分：${creditUser?.username || ''}`} open={!!creditUser} onCancel={() => { if (!actions.pending) setCreditUser(null); }} onOk={() => creditForm.submit()} okText="确认调整" cancelText="取消" modalRender={modalFocus} confirmLoading={actions.pending} closable={!actions.pending} maskClosable={!actions.pending}>
      {actions.error && <Alert type="error" title={actions.error} className="page-error" />}<Form form={creditForm} name="adminCredits" layout="vertical" requiredMark={false} disabled={actions.pending} onFinish={async values => { try { await actions.run(`/admin/api/users/${creditUser!.id}/credits`, 'POST', values); setCreditUser(null); actions.message.success('积分已调整'); state.refresh(); } catch { /* Keep inputs. */ } }}><Form.Item name="amount" label="调整数量" extra="正数增加，负数扣减" rules={[{ required: true, message: '请输入数量' }, { validator: (_, value) => Number.isInteger(value) && value !== 0 ? Promise.resolve() : Promise.reject(new Error('请输入非零整数')) }]}><InputNumber precision={0} /></Form.Item><Form.Item name="description" label="调整原因" rules={[{ required: true, whitespace: true, message: '请填写原因' }]}><Input /></Form.Item></Form>
    </Modal>
    <Modal title="临时密码" open={!!secret} onCancel={() => setSecret('')} onOk={() => setSecret('')} okText="已保存" cancelButtonProps={{ style: { display: 'none' } }} modalRender={modalFocus}><Alert type="warning" title="请妥善保存并通知用户及时修改密码。" /><div className="admin-secret"><code>{secret}</code><Button onClick={async () => { try { await copyText(secret); actions.message.success('临时密码已复制'); } catch (reason) { actions.message.error((reason as Error).message); } }}>复制临时密码</Button></div></Modal>
  </AdminPage>;
}

export default function AdminUsers({ data }: { data: ApiData }) {
  return data.user?.is_admin ? <Users data={data} /> : <Result status="403" title="需要管理员权限" />;
}
