import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Card, Divider, Form, Input, Result, Space, Tabs } from 'antd';
import { GithubOutlined } from '@ant-design/icons';
import { request, type ApiData } from '../api';
import { postForm } from '../forms';
import { Turnstile } from '../components/turnstile';

function CodeForm({ data, register, active }: { data: ApiData; register: boolean; active: boolean }) {
  const [form] = Form.useForm();
  const [sending, setSending] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const locked = useRef(false);
  const submitted = useRef(false);
  const [unlocked, setUnlocked] = useState(!!(data.registerError || data.registerUsername));
  const [notice, setNotice] = useState<{ type: 'error' | 'success'; text: string } | null>(null);
  const [token, setToken] = useState('');
  const [reset, setReset] = useState(0);
  const [ends, setEnds] = useState(0);
  const [now, setNow] = useState(Date.now());
  const countdown = Math.max(0, Math.ceil((ends - now) / 1000));
  useEffect(() => {
    if (!ends) return;
    const timer = setInterval(() => { const time = Date.now(); setNow(time); if (time >= ends) setEnds(0); }, 1000); return () => clearInterval(timer);
  }, [ends]);
  async function sendCode() {
    if (locked.current || countdown > 0) return;
    locked.current = true;
    let values: ApiData;
    try { values = await form.validateFields(register ? ['email', 'invite_code'] : ['email']); }
    catch { locked.current = false; return; }
    if (data.turnstileEnabled && !token) { setNotice({ type: 'error', text: '请先完成人机验证，通过后才可发送验证码' }); locked.current = false; return; }
    setSending(true); setNotice(null);
    try {
      const result = await request('/auth/api/send-code', 'POST', { email: values.email.trim(), code_type: register ? 'register' : 'reset', ...(register ? { invite_code: values.invite_code?.trim() || '' } : {}), turnstile_token: token });
      if (result.success !== true) throw new Error(result.message || '验证码发送失败');
      setNotice({ type: 'success', text: '验证码已发送到您的邮箱，请查收' }); const time = Date.now(); setNow(time); setEnds(time + 60000); setUnlocked(true);
    } catch (error) { setNotice({ type: 'error', text: (error as Error).message }); setReset(previous => previous + 1); }
    finally { if (!register) setReset(previous => previous + 1); locked.current = false; setSending(false); }
  }
  async function oauth(event: React.MouseEvent, provider: string) {
    event.preventDefault();
    try {
      const { invite_code } = await form.validateFields(['invite_code']);
      const url = new URL(`/auth/${provider}/login`, location.origin);
      if (invite_code?.trim()) url.searchParams.set('invite_code', invite_code.trim());
      location.href = url.toString();
    } catch { form.scrollToField('invite_code', { focus: true }); }
  }
  if (register && !data.registrationEnabled) return <Result status="403" title="注册已关闭" subTitle="管理员已关闭用户自助注册。" extra={<Button href="/auth/login?tab=login">返回登录</Button>} />;
  const error = register ? data.registerError : data.error;
  const newPassword = register ? 'password' : 'new_password';
  return <>
    <div className="auth-heading"><h1>{register ? '创建账户' : '重置密码'}</h1><p className="subtle">{register ? '通过邮件验证码完成注册' : '通过注册邮箱验证后设置新密码'}</p></div>
    {error && <Alert type="error" title={error} showIcon className="page-error" />}{data.success && <Alert type="success" title={data.success} showIcon className="page-error" />}
    {notice && <Alert type={notice.type} title={notice.text} showIcon className="page-error" />}
    <Form name={register ? 'registerForm' : 'resetForm'} form={form} layout="vertical" requiredMark={false} disabled={submitting} initialValues={{ email: register ? data.registerEmail : data.email, invite_code: data.inviteCode || '', username: data.registerUsername || '' }} scrollToFirstError onFinish={values => {
      if (submitted.current) return;
      if (register && !unlocked) { setNotice({ type: 'error', text: '请先发送验证码' }); return; }
      submitted.current = true; setSubmitting(true);
      postForm(register ? '/auth/register' : '/auth/reset-password', { ...values, turnstile_token: token, ...(register && data.mode === 'login' ? { ui: 'login' } : {}) });
    }}>
      {register && <Form.Item name="invite_code" label={data.inviteRequired ? '邀请码' : '邀请码（选填）'} rules={data.inviteRequired ? [{ required: true, whitespace: true, message: '请输入邀请码' }] : []}><Input autoComplete="off" placeholder={data.inviteRequired ? '输入邀请码后再注册' : '可选：填写邀请码领取邀请奖励'} /></Form.Item>}
      {register && (data.github || data.linuxdo) && <Space wrap className="auth-oauth">
        {data.github && <Button href="/auth/github/login" icon={<GithubOutlined aria-hidden />} onClick={event => oauth(event, 'github')}>GitHub 注册</Button>}
        {data.linuxdo && <Button href="/auth/linuxdo/login" onClick={event => oauth(event, 'linuxdo')}>LinuxDo 注册</Button>}
      </Space>}
      <Form.Item name="email" label="邮箱地址" rules={[{ required: true, message: '请输入邮箱地址' }, { type: 'email', message: '请输入有效的邮箱地址' }]}><Input type="email" autoComplete="email" placeholder="your@email.com" /></Form.Item>
      {data.turnstileEnabled && <Turnstile siteKey={data.turnstileSiteKey} active={active} reset={reset} onToken={setToken} />}
      <div className="auth-code-row"><Form.Item name="code" label="验证码" rules={[{ required: true, message: '请输入验证码' }]}><Input maxLength={6} inputMode="numeric" autoComplete="one-time-code" placeholder="6 位验证码" /></Form.Item><Button loading={sending} disabled={submitting || countdown > 0} onClick={sendCode}>{countdown > 0 ? `${countdown}s 后重发` : '发送验证码'}</Button></div>
      {(!register || unlocked) && <>
        {register && <Form.Item name="username" label="用户名" rules={[{ required: true, whitespace: true, message: '请输入用户名' }, { min: 3, max: 20, message: '用户名长度需为 3–20 个字符' }]}><Input autoComplete="username" maxLength={20} /></Form.Item>}
        <Form.Item name={newPassword} label={register ? '密码' : '新密码'} rules={[{ required: true, message: '请输入密码' }, { min: 6, message: '密码长度至少 6 位' }]}><Input.Password autoComplete="new-password" /></Form.Item>
        <Form.Item name="confirm_password" label={register ? '确认密码' : '确认新密码'} dependencies={[newPassword]} rules={[{ required: true, message: '请再次输入密码' }, ({ getFieldValue }) => ({ validator: (_, value) => !value || value === getFieldValue(newPassword) ? Promise.resolve() : Promise.reject(new Error('两次密码输入不一致')) })]}><Input.Password autoComplete="new-password" /></Form.Item>
        <Button type="primary" htmlType="submit" loading={submitting} block>{register ? '注册' : '重置密码'}</Button>
      </>}
    </Form>
    {!register && <div className="auth-links"><a href="/auth/login">返回登录</a><a href="/auth/login?tab=register">注册新账户</a></div>}
  </>;
}

export default function Auth({ data }: { data: ApiData }) {
  const [tab, setTab] = useState(data.activeTab === 'register' ? 'register' : 'login');
  const [submitting, setSubmitting] = useState(false);
  const submitted = useRef(false);
  const login = <>
    <div className="auth-heading"><h1>欢迎回来</h1><p className="subtle">登录后继续创作演示文稿</p></div>
    {data.error && <Alert type="error" title={data.error} showIcon className="page-error" />}{data.success && <Alert type="success" title={data.success} showIcon className="page-error" />}
    <Form id="loginFormElement" layout="vertical" requiredMark={false} disabled={submitting} initialValues={{ username: data.username || '' }} onFinish={values => { if (submitted.current) return; submitted.current = true; setSubmitting(true); postForm('/auth/login', values); }}>
      <Form.Item name="username" label="用户名或邮箱" htmlFor="username" rules={[{ required: true, whitespace: true, message: '请输入用户名或邮箱' }]}><Input id="username" autoComplete="username" placeholder="输入用户名或邮箱" /></Form.Item>
      <Form.Item name="password" label="密码" htmlFor="password" rules={[{ required: true, message: '请输入密码' }]}><Input.Password id="password" autoComplete="current-password" placeholder="输入密码" /></Form.Item><Button type="primary" htmlType="submit" loading={submitting} block>登录</Button>
    </Form>
    {(data.github || data.linuxdo) && <><Divider plain>或</Divider><div className="auth-oauth">{data.github && <Button href="/auth/github/login" block icon={<GithubOutlined aria-hidden />}>使用 GitHub 登录</Button>}{data.linuxdo && <Button href="/auth/linuxdo/login" block>使用 Linux Do 登录</Button>}</div></>}
    <div className="auth-links"><a href="/auth/forgot-password">忘记密码？</a><a href="/auth/login?tab=register">没有账号，去注册</a></div>
  </>;
  return <div className="auth-page"><Card className="form-shell">
    {data.mode === 'reset' ? <CodeForm data={data} register={false} active /> : data.mode === 'register' ? <CodeForm data={data} register active /> : <Tabs activeKey={tab} onChange={key => { setTab(key); const url = new URL(location.href); url.searchParams.set('tab', key); history.replaceState(null, '', url); }} items={[
      { key: 'login', label: '登录', children: login }, { key: 'register', label: '注册', children: <CodeForm data={data} register active={tab === 'register'} /> },
    ]} />}
  </Card></div>;
}
