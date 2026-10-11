export type ApiData = Record<string, any>;

export function errorText(value: unknown): string {
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return value.map(errorText).join('；');
  if (value && typeof value === 'object') {
    const data = value as ApiData;
    return typeof data.msg === 'string' ? data.msg : typeof data.message === 'string' ? data.message : JSON.stringify(data);
  }
  return '请求失败，请稍后重试';
}

export async function request(url: string, method = 'GET', body?: unknown, signal?: AbortSignal): Promise<ApiData> {
  const response = await fetch(url, {
    method, credentials: 'same-origin', signal,
    headers: { Accept: 'application/json', ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.success === false || data.status === 'error') {
    throw new Error(errorText(data.detail || data.error || data.errors || data.message || `请求失败（${response.status}）`));
  }
  return data;
}
