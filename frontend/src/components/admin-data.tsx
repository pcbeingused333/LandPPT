import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Alert, App, Button, Card, Empty, Pagination, Space, Table, type TableProps } from 'antd';
import { request, type ApiData } from '../api';
import { modalFocus } from './modal-focus';

export function useAdminList(endpoint: string, key: string, params: ApiData) {
  const [rows, setRows] = useState<ApiData[]>([]); const [total, setTotal] = useState(0); const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true); const [error, setError] = useState('');
  const reading = useRef<AbortController | null>(null); const latest = useRef<ApiData>({ ...params, page: 1 });
  const signature = JSON.stringify(params);
  async function load(target = latest.current) {
    reading.current?.abort(); const controller = new AbortController(); reading.current = controller; latest.current = target;
    setLoading(true); setError('');
    const query = new URLSearchParams(Object.entries(target).filter(([, value]) => value !== '' && value != null).map(([name, value]) => [name, String(value)]));
    try {
      const data = await request(endpoint + '?' + query, 'GET', undefined, controller.signal);
      if (controller.signal.aborted) return;
      const count = Number(data.total || 0); const last = Math.max(1, Math.ceil(count / Number(target.page_size || 20)));
      if (Number(target.page) > last) { await load({ ...target, page: last }); return; }
      setRows(data[key] || []); setTotal(count); setPage(Number(data.page || target.page || 1));
    } catch (reason) { if (!controller.signal.aborted) setError((reason as Error).message); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  }
  useEffect(() => { load({ ...params, page: 1 }); return () => reading.current?.abort(); }, [endpoint, key, signature]);
  return { rows, total, page, loading, error, refresh: () => load(), retry: () => load(), changePage: (page: number) => load({ ...latest.current, page }) };
}

export function useAdminActions() {
  const { message, modal } = App.useApp(); const [pending, setPending] = useState(false); const [error, setError] = useState('');
  const locked = useRef(false); const confirming = useRef(false);
  async function run(url: string, method: string, body?: ApiData) {
    if (locked.current) throw new Error('请等待当前操作完成');
    locked.current = true; setPending(true); setError('');
    try { return await request(url, method, body); }
    catch (reason) { setError((reason as Error).message); throw reason; }
    finally { locked.current = false; setPending(false); }
  }
  function confirm(title: string, content: ReactNode, action: () => Promise<void>, danger = false) {
    if (confirming.current || locked.current) return;
    confirming.current = true;
    modal.confirm({ title, content, okText: '确认', cancelText: '取消', okButtonProps: { danger }, modalRender: modalFocus, afterClose: () => { confirming.current = false; }, onOk: async () => {
      try { await action(); } catch (reason) { message.error((reason as Error).message); throw reason; }
    } });
  }
  return { pending, error, run, confirm, message, clearError: () => setError('') };
}

export function AdminCollection({ state, columns, card, pageSize }: { state: ReturnType<typeof useAdminList>; columns: TableProps<ApiData>['columns']; card: (row: ApiData) => ReactNode; pageSize: number }) {
  return <>{state.error && <Alert type="error" title={state.error} action={<Button onClick={state.retry}>重试</Button>} className="page-error" />}
    <div className="account-table"><Table<ApiData> size="small" rowKey="id" loading={state.loading} columns={columns} dataSource={state.rows} pagination={false} scroll={{ x: 960 }} locale={{ emptyText: <Empty description="暂无数据" /> }} /></div>
    <div className="account-mobile-list">{state.loading && <p role="status">正在加载…</p>}{state.rows.length ? state.rows.map(row => <Card size="small" key={row.id}>{card(row)}</Card>) : !state.loading && <Empty description="暂无数据" />}</div>
    <Space className="projects-pagination"><span className="subtle">共 {state.total} 条</span><Pagination current={state.page} total={state.total} pageSize={pageSize} showSizeChanger={false} showLessItems disabled={state.loading} onChange={state.changePage} /></Space>
  </>;
}
