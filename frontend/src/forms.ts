import type { ApiData } from './api';

// Keep HTML form routes, cookies and server-rendered redirects unchanged.
export function postForm(url: string, values: ApiData) {
  const form = document.createElement('form');
  form.method = 'POST'; form.action = url; form.hidden = true;
  for (const [name, value] of Object.entries(values)) {
    if (value == null) continue;
    const input = document.createElement('input');
    input.type = 'hidden'; input.name = name; input.value = String(value); form.append(input);
  }
  document.body.append(form); form.submit();
}

export function formatTime(value: unknown) {
  if (value == null || value === '') return '—';
  const date = new Date(typeof value === 'number' ? value * 1000 : String(value));
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('zh-CN');
}

export async function copyText(value: string) {
  if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(value); return; }
  const previous = document.activeElement as HTMLElement | null;
  const field = document.createElement('textarea'); field.value = value;
  field.style.position = 'fixed'; field.style.opacity = '0'; document.body.append(field);
  try {
    field.focus(); field.select();
    if (!document.execCommand('copy')) throw new Error('复制失败，请手动选择内容复制');
  } finally { field.remove(); previous?.focus(); }
}

export function safeWebURL(value: unknown) {
  try { const url = new URL(String(value || ''), location.origin); return value && ['https:', 'http:'].includes(url.protocol) ? url.href : undefined; } catch { return undefined; }
}
