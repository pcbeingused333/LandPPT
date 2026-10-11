import { type ReactNode, useEffect, useRef, useState } from 'react';
import { App, type FormInstance } from 'antd';
import { request, type ApiData } from '../api';

export function AdminPage({ title, description, credits, children, className = '' }: { title: string; description: string; credits: boolean; children: ReactNode; className?: string }) {
  const links = [['用户', '/admin/users'], ...(credits ? [['积分', '/admin/credits']] : []), ['运营', '/admin/community'], ['OAuth', '/admin/oauth'], ['邮件', '/admin/smtp']];
  return <div className={'admin-page settings-page ' + className}><nav className="admin-navigation" aria-label="管理后台">{links.map(([label, href]) => <a key={href} href={href} aria-current={location.pathname === href ? 'page' : undefined}>{label}</a>)}</nav>
    <div className="page-heading"><div><h1>{title}</h1><p>{description}</p></div></div>{children}
  </div>;
}

export function useAdminConfig(endpoint: string, form: FormInstance, normalize: (config: ApiData) => ApiData, responseKey = 'config') {
  const { message } = App.useApp();
  const [loading, setLoading] = useState(true);
  const [ready, setReady] = useState(false);
  const [readError, setReadError] = useState('');
  const [error, setError] = useState('');
  const [pending, setPending] = useState('');
  const reading = useRef<AbortController | null>(null);
  const locked = useRef(false);
  const normalizeRef = useRef(normalize); normalizeRef.current = normalize;
  async function load(replace = false) {
    if (locked.current) return;
    reading.current?.abort(); const controller = new AbortController(); reading.current = controller;
    setLoading(true); setReadError('');
    try {
      const data = await request(endpoint, 'GET', undefined, controller.signal);
      if (controller.signal.aborted) return;
      const values = normalizeRef.current(data[responseKey] || {});
      form.setFields(Object.entries(values).filter(([name]) => replace || !form.isFieldTouched(name)).map(([name, value]) => ({ name, value, touched: false, errors: [] })));
      setReady(true);
    } catch (reason) { if (!controller.signal.aborted) setReadError((reason as Error).message); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  }
  useEffect(() => { load(); return () => reading.current?.abort(); }, [endpoint, responseKey]);
  async function mutate(kind: string, body: ApiData, suffix = '', options: { endpoint?: string; success?: string | false } = {}) {
    if (locked.current || loading || !ready) return null;
    locked.current = true; setPending(kind); setError('');
    try {
      const result = await request(options.endpoint || endpoint + suffix, 'POST', body);
      if (result.success !== true) throw new Error(result.message || '操作失败');
      if (options.success !== false) message.success(result.message || options.success || '设置已保存'); return result;
    } catch (reason) { setError((reason as Error).message); return null; }
    finally { locked.current = false; setPending(''); }
  }
  return { loading, ready, pending, readError, error, load, mutate };
}
