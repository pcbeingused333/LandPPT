import { useState } from 'react';
import { App, Button, Image, Space } from 'antd';
import { CopyOutlined, DownloadOutlined } from '@ant-design/icons';
import { copyText } from '../forms';
import { errorText } from '../api';

export const imageSources = [
  { value: 'ai_generated', label: 'AI 生成' }, { value: 'web_search', label: '网络搜索' }, { value: 'local_storage', label: '本地上传' },
];
export const uploadCategories = [
  ['business', '商务'], ['technology', '技术'], ['education', '教育'], ['design', '设计'], ['nature', '自然'], ['people', '人物'], ['abstract', '抽象'], ['other', '其他'],
].map(([value, label]) => ({ value, label }));
export function sourceLabel(value: string) { return imageSources.find(item => item.value === value)?.label || value || '—'; }
export function fileSize(value: number) {
  if (!Number.isFinite(value) || value < 0) return '—';
  return value < 1024 ? `${value} B` : value < 1048576 ? `${+(value / 1024).toFixed(1)} KB` : `${+(value / 1048576).toFixed(1)} MB`;
}
export function imageEndpoint(kind: string, id: string) { return `/api/image/${kind}/${encodeURIComponent(id)}`; }

export async function downloadImageFile(url: string, body?: { image_ids: string[] }) {
  const response = await fetch(url, {
    method: body ? 'POST' : 'GET', credentials: 'same-origin',
    ...(body ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}),
  });
  if (!response.ok || response.headers.get('Content-Type')?.includes('application/json')) {
    const error = await response.json().catch(() => ({}));
    throw new Error(errorText(error.detail || error.message || `下载失败（${response.status}）`));
  }
  const disposition = response.headers.get('Content-Disposition') || '';
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  let filename = disposition.match(/filename="([^"]+)"/i)?.[1] || (body ? 'images.zip' : 'image');
  if (encoded) { try { filename = decodeURIComponent(encoded); } catch { /* Use the plain filename. */ } }
  const objectURL = URL.createObjectURL(await response.blob());
  const link = document.createElement('a'); link.href = objectURL; link.download = filename; document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(objectURL), 1000);
}

export function ImageActions({ url, downloadURL, disabled = false }: { url: string; downloadURL?: string; disabled?: boolean }) {
  const { message } = App.useApp(); const [downloading, setDownloading] = useState(false);
  return <Space className="image-actions" wrap>
    <Button icon={<CopyOutlined aria-hidden />} disabled={disabled} onClick={async () => {
      try { await copyText(new URL(url, location.origin).href); message.success('图片链接已复制'); } catch (reason) { message.error((reason as Error).message); }
    }}>复制链接</Button>
    <Button icon={<DownloadOutlined aria-hidden />} disabled={disabled} loading={downloading} onClick={async () => {
      if (downloading) return; setDownloading(true);
      try { await downloadImageFile(downloadURL || url); } catch (reason) { message.error((reason as Error).message); } finally { setDownloading(false); }
    }}>下载</Button>
  </Space>;
}

export function ImagePreview({ src, title }: { src: string; title: string }) {
  return <Image className="asset-preview-image" src={src} alt={title} preview={false} fallback="/static/images/placeholder.svg" />;
}
