import type { ApiData } from './api';

type InitialRead = { identity: string; controller: AbortController; response: Promise<Response> };
let initialRead: InitialRead | undefined;
const identity = (data: ApiData) => JSON.stringify([data.user?.username || '', !!data.user?.is_admin]);
const read = (signal: AbortSignal) => fetch('/create', { credentials: 'same-origin', cache: 'no-store', signal, headers: { Accept: 'text/html' } });

// Start the dashboard's required settings read alongside its JS, then hand it
// to the first composer. This is a single-use response, never a page-data cache.
export function primeCreationConfiguration(data: ApiData) {
  if (data.page !== 'dashboard') return;
  initialRead?.controller.abort();
  const controller = new AbortController();
  const response = read(controller.signal);
  void response.catch(() => {}); // The composer displays errors and offers retry.
  initialRead = { identity: identity(data), controller, response };
}

export async function readCreationConfiguration(data: ApiData, signal: AbortSignal) {
  const primed = initialRead; initialRead = undefined;
  const matching = primed?.identity === identity(data) ? primed : undefined;
  if (!matching) primed?.controller.abort();
  const abort = () => matching?.controller.abort();
  if (matching) signal.addEventListener('abort', abort, { once: true });
  if (signal.aborted) abort();
  try {
    const response = await (matching?.response || read(signal));
    if (!response.ok) throw new Error('暂时无法加载创建设置');
    const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
    const value = JSON.parse(doc.getElementById('antdData')?.textContent || 'null');
    if (value?.page !== 'create-project' || identity(value) !== identity(data)) throw new Error('创建设置不可用，请刷新页面重试');
    return value as ApiData;
  } finally { signal.removeEventListener('abort', abort); }
}

export function discardInitialCreationConfiguration() {
  initialRead?.controller.abort(); initialRead = undefined;
}
