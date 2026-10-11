import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Spin } from 'antd';

interface TurnstileApi {
  render(node: HTMLElement, options: Record<string, unknown>): string;
  remove(id: string): void;
}
declare global { interface Window { turnstile?: TurnstileApi; } }
let loading: Promise<TurnstileApi> | null = null;
function loadApi() {
  if (window.turnstile) return Promise.resolve(window.turnstile);
  if (loading) return loading;
  loading = new Promise<TurnstileApi>((resolve, reject) => {
    const script = document.createElement('script');
    let settled = false;
    const fail = () => { if (settled) return; settled = true; clearTimeout(timeout); script.remove(); reject(new Error('人机验证加载失败，请检查网络后重试')); };
    const timeout = setTimeout(fail, 12000);
    script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'; script.async = true;
    script.onload = () => { if (settled) return; if (!window.turnstile) { fail(); return; } settled = true; clearTimeout(timeout); resolve(window.turnstile); }; script.onerror = fail;
    document.head.append(script);
  }).catch(error => { loading = null; throw error; });
  return loading;
}

export function Turnstile({ siteKey, active, reset, onToken }: { siteKey: string; active: boolean; reset: number; onToken: (token: string) => void }) {
  const container = useRef<HTMLDivElement>(null);
  const callback = useRef(onToken); callback.current = onToken;
  const [error, setError] = useState('');
  const [waiting, setWaiting] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!active || !siteKey) return;
    let disposed = false; let id: string | undefined; let api: TurnstileApi | undefined;
    setError(''); setWaiting(true); callback.current('');
    loadApi().then(instance => {
      if (disposed || !container.current) return;
      api = instance;
      id = api.render(container.current, { sitekey: siteKey, theme: 'light', language: 'zh-CN', size: container.current.clientWidth < 300 ? 'compact' : 'normal', 'response-field': false,
        callback: (token: string) => { if (!disposed) { callback.current(token); setError(''); } },
        'expired-callback': () => { if (!disposed) callback.current(''); },
        'error-callback': (code: string) => { if (!disposed) { callback.current(''); setError(`人机验证失败（${code}），请重试`); } },
      });
      setWaiting(false);
    }).catch(error => { if (!disposed) { setWaiting(false); setError((error as Error).message); } });
    return () => { disposed = true; if (id && api) api.remove(id); callback.current(''); };
  }, [siteKey, active, reset, retry]);
  return <div className="auth-turnstile">{active && waiting && <p role="status"><Spin size="small" /> 正在加载人机验证…</p>}<div ref={container} aria-label="Turnstile 人机验证" />{active && error && <Alert type="error" title={error} action={<Button onClick={() => setRetry(previous => previous + 1)}>重试</Button>} />}</div>;
}
