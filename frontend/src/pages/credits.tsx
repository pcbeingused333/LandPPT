import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Card, Empty, Pagination, Space, Table, Tag } from 'antd';
import { request, type ApiData } from '../api';
import { CreditActions } from '../components/credit-actions';
import { formatTime } from '../forms';

const typeLabels: Record<string, string> = { consume: '消耗', recharge: '充值', redemption: '兑换', admin_adjust: '管理员调整', refund: '退款', daily_checkin: '每日签到', invite_reward: '邀请码赠送' };

export default function Credits({ data }: { data: ApiData }) {
  const [stats, setStats] = useState<ApiData>({ balance: data.balance, total_consumed: null, total_recharged: null });
  const [statsError, setStatsError] = useState('');
  const [pricing, setPricing] = useState<ApiData>({});
  const [pricingError, setPricingError] = useState('');
  const [records, setRecords] = useState<ApiData[]>([]);
  const [recordError, setRecordError] = useState('');
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const statsController = useRef<AbortController | null>(null);
  const recordsController = useRef<AbortController | null>(null);
  const recordsTarget = useRef(1);
  const pricingController = useRef<AbortController | null>(null);
  async function loadStats() {
    statsController.current?.abort(); const controller = new AbortController(); statsController.current = controller; setStatsError('');
    try { const result = await request('/credits/api/balance', 'GET', undefined, controller.signal); if (!controller.signal.aborted) setStats(result); }
    catch (error) { if (!controller.signal.aborted) setStatsError((error as Error).message); }
  }
  async function loadPricing() {
    pricingController.current?.abort(); const controller = new AbortController(); pricingController.current = controller; setPricingError('');
    try { const result = await request('/credits/api/pricing', 'GET', undefined, controller.signal); if (!controller.signal.aborted) setPricing(result.pricing || {}); }
    catch (error) { if (!controller.signal.aborted) setPricingError((error as Error).message); }
  }
  async function loadRecords(target = 1) {
    recordsTarget.current = target;
    recordsController.current?.abort(); const controller = new AbortController(); recordsController.current = controller; setLoading(true); setRecordError('');
    try {
      const result = await request(`/credits/api/transactions?page=${target}&page_size=20`, 'GET', undefined, controller.signal);
      if (!controller.signal.aborted) { setRecords(result.transactions || []); setTotal(result.total ?? (result.total_pages || 0) * 20); setPage(target); }
    } catch (error) { if (!controller.signal.aborted) setRecordError((error as Error).message); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  }
  useEffect(() => {
    loadStats(); loadPricing(); loadRecords();
    return () => { statsController.current?.abort(); pricingController.current?.abort(); recordsController.current?.abort(); };
  }, []);
  const amount = (record: ApiData) => <span className={record.amount < 0 ? 'credit-amount-negative' : 'credit-amount-positive'}>{record.amount >= 0 ? '+' : ''}{record.amount}</span>;
  return <div className="account-page credits-page">
    <div className="page-heading"><div><h1>我的积分</h1><p>查看余额、兑换和交易记录</p></div><Button href="/auth/profile#credits">个人资料</Button></div>
    {statsError && <Alert type="error" showIcon title={statsError} action={<Button onClick={loadStats}>重试</Button>} className="page-error" />}
    <div className="stats-grid credits-stats">{[['当前余额', 'balance'], ['累计消耗', 'total_consumed'], ['累计充值', 'total_recharged']].map(([label, field]) => <div className="stat-card" key={field}><span className="stat-title">{label}</span><strong className="stat-number">{stats[field] == null ? '—' : Number(stats[field]).toLocaleString()}</strong></div>)}</div>
    <CreditActions onBalance={balance => setStats(previous => ({ ...previous, balance }))} onChanged={() => { loadStats(); loadRecords(1); }} />
    <Card size="small" title="计费参考" className="credit-pricing">{pricingError ? <Alert type="error" title={pricingError} action={<Button onClick={loadPricing}>重试</Button>} /> : Object.keys(pricing).length ? <div className="credit-pricing-grid">{Object.entries(pricing).map(([key, value]) => <div key={key}><strong>{value.cost} 积分</strong><p className="subtle">{value.description}</p></div>)}</div> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无计费参考" />}</Card>
    <div className="section-heading"><h2>交易明细</h2><Button disabled={loading} onClick={() => loadRecords(page)}>刷新</Button></div>
    {recordError && <Alert type="error" title={recordError} action={<Button onClick={() => loadRecords(recordsTarget.current)}>重试</Button>} className="page-error" />}
    <div className="account-table"><Table<ApiData> size="small" loading={loading} rowKey="id" dataSource={records} pagination={false} locale={{ emptyText: <Empty description="暂无交易记录" /> }} columns={[
      { title: '时间', width: 190, render: (_, record) => formatTime(record.created_at) }, { title: '类型', width: 140, render: (_, record) => typeLabels[record.transaction_type] || record.transaction_type },
      { title: '说明', dataIndex: 'description' }, { title: '变动', width: 90, render: (_, record) => amount(record) }, { title: '余额', dataIndex: 'balance_after', width: 90 },
    ]} /></div>
    <div className="account-mobile-list">{loading && <p role="status" className="subtle">正在加载交易记录…</p>}{records.length ? records.map(record => <Card size="small" key={record.id}><div className="credit-record-heading"><Tag>{typeLabels[record.transaction_type] || record.transaction_type}</Tag>{amount(record)}</div><p>{record.description}</p><div className="credit-record-meta subtle"><span>{formatTime(record.created_at)}</span><span>余额：{record.balance_after}</span></div></Card>) : !loading && <Empty description="暂无交易记录" />}</div>
    <Space className="projects-pagination credits-pagination"><Pagination current={page} total={total} pageSize={20} showSizeChanger={false} showLessItems disabled={loading} onChange={loadRecords} /></Space>
  </div>;
}
