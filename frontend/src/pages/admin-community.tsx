import { useEffect, useState, type ReactNode } from 'react';
import { Alert, Button, Card, Form, Input, InputNumber, Radio, Result, Space, Switch, Tabs } from 'antd';
import type { ApiData } from '../api';
import { AdminPage, useAdminConfig } from '../components/admin';
import { booleanValue } from '../community-schema';
import SystemDefaults from './community-system';
import Invites from './community-invites';
import Sponsors from './community-sponsors';

const defaults: ApiData = { daily_checkin_enabled: false, daily_checkin_reward_mode: 'fixed', daily_checkin_reward_fixed: 5, daily_checkin_reward_min: 2, daily_checkin_reward_max: 8, invite_code_required_for_registration: false, sponsor_page_enabled: false, site_notice_enabled: false, site_notice_level: 'info', site_notice_title: '', site_notice_message: '', site_notice_start_at: '', site_notice_end_at: '' };
const tabKeys = ['system-defaults', 'notice', 'checkin', 'invites', 'sponsors'];
const fromHash = () => tabKeys.includes(location.hash.slice(1)) ? location.hash.slice(1) : 'system-defaults';
function localDate(value: unknown) {
  if (value == null || value === '') return '';
  const date = new Date(Number(value) * 1000);
  return Number.isNaN(date.getTime()) ? '' : new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
function normalize(config: ApiData) {
  return Object.fromEntries(Object.entries(defaults).map(([key, fallback]) => [key, key.endsWith('_at') ? localDate(config[key]) : typeof fallback === 'boolean' ? booleanValue(config[key] ?? fallback) : config[key] ?? fallback]));
}
function Operations({ data }: { data: ApiData }) {
  const [active, setActive] = useState(fromHash); const [form] = Form.useForm();
  const state = useAdminConfig('/admin/api/community/settings', form, normalize, 'settings');
  const values = Form.useWatch([], { form, preserve: true }) || defaults;
  const blocked = !state.ready || state.loading || !!state.pending;
  useEffect(() => { const sync = () => setActive(fromHash()); window.addEventListener('hashchange', sync); return () => window.removeEventListener('hashchange', sync); }, []);
  async function save() {
    try { await form.validateFields(); } catch { return; }
    const all = { ...defaults, ...form.getFieldsValue(true) }; const payload: ApiData = {};
    for (const [key, fallback] of Object.entries(defaults)) {
      const value = all[key];
      payload[key] = key.endsWith('_at') ? value ? Math.floor(new Date(value).getTime() / 1000) : null : typeof fallback === 'boolean' ? !!value : typeof fallback === 'number' ? Number(value ?? 0) : String(value || '').trim();
    }
    const result = await state.mutate('save', payload, '', { success: '运营配置已保存' });
    if (result) window.dispatchEvent(new Event('landppt:community-settings-saved'));
  }
  const saveBar = <div className="settings-savebar"><span className="subtle" role="status">{state.loading ? '正在读取运营配置…' : '保存公告、签到、注册及赞助页的全部设置'}</span><Space><Button disabled={state.loading || !!state.pending} onClick={() => state.load(true)}>重新加载</Button><Button type="primary" disabled={blocked} loading={state.pending === 'save'} onClick={save}>保存全部运营配置</Button></Space></div>;
  const settings = (children: ReactNode) => <div className="settings-stack">{saveBar}{state.readError && <Alert type="error" title="运营配置加载失败" description={state.readError} action={<Button onClick={() => state.load()}>重试</Button>} />}{state.error && <Alert type="error" title={state.error} />}{children}</div>;
  const toggle = (name: string, label: string, help?: string) => <Form.Item name={name} label={label} extra={help} valuePropName="checked"><Switch disabled={!!state.pending} /></Form.Item>;
  return <AdminPage title="运营设置" description="管理系统默认值、公告、注册与赞助展示" credits={data.creditsEnabled} className="admin-community-page">
    {!data.creditsEnabled && <Alert className="page-error" type="info" title="积分系统未启用，签到奖励与邀请码赠分暂不生效。" />}
    <Form form={form} component="div" layout="vertical" requiredMark={false} initialValues={defaults} disabled={!!state.pending}>
      <Tabs activeKey={active} onChange={key => { setActive(key); history.replaceState(null, '', '#'+key); }} items={[
        { key: 'system-defaults', label: '系统默认配置', children: <SystemDefaults /> },
        { key: 'notice', label: '站内公告', children: settings(<Card size="small" title="站内公告">{toggle('site_notice_enabled', '开启站内公告', '保存后展示在主要业务页及登录、注册页顶部。')}<Form.Item name="site_notice_level" label="公告类型"><Radio.Group options={[{ value: 'info', label: '信息' }, { value: 'success', label: '成功' }, { value: 'warning', label: '提醒' }, { value: 'danger', label: '警告' }]} /></Form.Item><Form.Item name="site_notice_title" label="公告标题"><Input /></Form.Item><Form.Item name="site_notice_message" label="公告内容"><Input.TextArea rows={4} /></Form.Item><div className="settings-fields"><Form.Item name="site_notice_start_at" label="开始时间" extra="留空立即生效"><Input type="datetime-local" /></Form.Item><Form.Item name="site_notice_end_at" label="结束时间" extra="留空长期展示"><Input type="datetime-local" /></Form.Item></div><Alert type={values.site_notice_level === 'danger' ? 'error' : values.site_notice_level === 'success' ? 'success' : values.site_notice_level === 'warning' ? 'warning' : 'info'} title={values.site_notice_title || '公告预览'} description={values.site_notice_message || '填写内容后可在此预览。'} className="community-preview" /></Card>) },
        { key: 'checkin', label: '每日签到', children: settings(<Card size="small" title="每日签到">{toggle('daily_checkin_enabled', '开启每日签到')}<Form.Item name="daily_checkin_reward_mode" label="签到奖励模式"><Radio.Group options={[{ value: 'fixed', label: '固定值' }, { value: 'random', label: '随机范围' }]} /></Form.Item><div className="settings-fields"><Form.Item name="daily_checkin_reward_fixed" label="固定奖励积分" extra="固定模式使用此值"><InputNumber min={0} precision={0} /></Form.Item><Form.Item name="daily_checkin_reward_min" label="随机最小积分"><InputNumber min={0} precision={0} /></Form.Item><Form.Item name="daily_checkin_reward_max" label="随机最大积分"><InputNumber min={0} precision={0} /></Form.Item></div><p className="subtle">当前规则：{values.daily_checkin_enabled ? values.daily_checkin_reward_mode === 'random' ? `${Math.min(values.daily_checkin_reward_min, values.daily_checkin_reward_max)} ~ ${Math.max(values.daily_checkin_reward_min, values.daily_checkin_reward_max)} 积分` : `${values.daily_checkin_reward_fixed} 积分` : '关闭'}</p></Card>) },
        { key: 'invites', label: '邀请码注册', children: settings(<><Card size="small" title="注册规则">{toggle('invite_code_required_for_registration', '新用户注册必须填写邀请码', '关闭后改为选填；用户填写后仍会校验并按规则发放奖励。')}</Card><Invites /></>) },
        { key: 'sponsors', label: '赞助感谢页', children: settings(<><Card size="small" title="公开展示">{toggle('sponsor_page_enabled', '公开赞助感谢页', '开启后点击上方“保存全部运营配置”，前台页脚才会显示“赞助感谢”入口。')}<Alert type="info" showIcon title="名单与页面开关分别保存" description="新增赞助不会自动公开页面。仅标记为“允许展示”的赞助者会出现在感谢页；页面未公开时，管理员也可预览。" className="page-error" /><Button href="/sponsors" target="_blank" rel="noopener">预览感谢页</Button></Card><Sponsors /></>) },
      ]} />
    </Form>
  </AdminPage>;
}
export default function AdminCommunity({ data }: { data: ApiData }) {
  return data.user?.is_admin ? <Operations data={data} /> : <Result status="403" title="需要管理员权限" />;
}
