import { useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Card, Form, Input, Space, Tag } from 'antd';
import { request, type ApiData } from '../api';

export function CreditActions({ onBalance, onChanged }: { onBalance: (value: number) => void; onChanged?: () => void }) {
  const { message } = App.useApp();
  const [status, setStatus] = useState<ApiData | null>(null);
  const [readError, setReadError] = useState('');
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState<'checkin' | 'redeem' | null>(null);
  const locked = useRef(false);
  const controller = useRef<AbortController | null>(null);
  const [form] = Form.useForm();
  async function refresh() {
    controller.current?.abort(); const next = new AbortController(); controller.current = next;
    setLoading(true); setReadError('');
    try { const result = await request('/credits/api/checkin-status', 'GET', undefined, next.signal); if (!next.signal.aborted) setStatus(result); }
    catch (error) { if (!next.signal.aborted) { setStatus(null); setReadError((error as Error).message); } }
    finally { if (!next.signal.aborted) setLoading(false); }
  }
  useEffect(() => { refresh(); return () => { controller.current?.abort(); }; }, []);
  async function mutate(kind: 'checkin' | 'redeem', values?: ApiData) {
    if (locked.current) return;
    locked.current = true; setPending(kind);
    try {
      const result = await request(`/credits/api/${kind}`, 'POST', kind === 'redeem' ? { code: values!.code.trim() } : undefined);
      if (result.success !== true) throw new Error(result.message || '操作失败');
      if (Number.isFinite(Number(result.new_balance))) onBalance(Number(result.new_balance));
      if (kind === 'redeem') form.resetFields();
      else setStatus(previous => ({ ...previous, ...result, already_checked_in: true }));
      message.success(result.message || (kind === 'redeem' ? '兑换成功' : '签到成功')); onChanged?.();
    } catch (error) { message.error((error as Error).message); if (kind === 'checkin') await refresh(); }
    finally { locked.current = false; setPending(null); }
  }
  return <div className="account-card-grid">
    <Card size="small" title="每日签到" extra={<Tag>{loading ? '加载中' : !status?.enabled ? '未开启' : status.already_checked_in ? '今日已签到' : '今日可签到'}</Tag>}>
      {readError ? <Alert type="error" showIcon title="签到状态获取失败" description={readError} action={<Button onClick={refresh}>重试</Button>} /> : <>
        <p className="subtle">{loading ? '正在获取签到规则…' : !status?.enabled ? '签到功能暂未开放' : status.already_checked_in ? `今天已领取 ${status.today_reward || 0} 积分` : `今日奖励：${status.reward_preview || '查看签到规则'}`}</p>
        <Button type="primary" loading={pending === 'checkin'} disabled={loading || !!pending || !status?.enabled || status.already_checked_in} onClick={() => mutate('checkin')}>{status?.already_checked_in ? '今日已签到' : '立即签到'}</Button>
      </>}
    </Card>
    <Card size="small" title="兑换码充值"><Form form={form} layout="vertical" requiredMark={false} disabled={!!pending} onFinish={values => mutate('redeem', values)}><Form.Item name="code" label="兑换码" rules={[{ required: true, whitespace: true, message: '请输入兑换码' }]}><Input autoComplete="off" placeholder="输入兑换码" /></Form.Item><Space><Button htmlType="submit" type="primary" loading={pending === 'redeem'}>兑换</Button><span className="subtle">兑换成功后更新余额</span></Space></Form></Card>
  </div>;
}
