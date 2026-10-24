// The small loader can be versioned independently. Shared page chunks import
// the hashed application entry, so there is only one React runtime/root URL.
import { discardInitialCreationConfiguration, primeCreationConfiguration } from './creation-config';

type Asset = { file?: string; imports?: string[] };
function preloadModules(manifest: Record<string, Asset>, page: string) {
  const visited = new Set<string>();
  const existing = new Set([...document.querySelectorAll<HTMLLinkElement>('link[rel="modulepreload"]')].map(link => link.href));
  const add = (key: string) => {
    if (visited.has(key)) return;
    visited.add(key);
    const asset = manifest[key];
    if (!asset || typeof asset.file !== 'string' || !/^(?:chunks\/)?[\w-]+\.js$/.test(asset.file)) return;
    const href = new URL(`/static/antd/${asset.file}`, location.origin).href;
    if (!existing.has(href)) {
      const link = document.createElement('link');
      link.rel = 'modulepreload'; link.crossOrigin = 'anonymous'; link.href = href;
      document.head.appendChild(link); existing.add(href);
    }
    asset.imports?.forEach(add);
  };
  add('src/main.tsx');
  const aliases: Record<string, string> = { 'generator-workspace': 'generator-chrome', 'template-selection': 'templates' };
  if (/^[a-z][a-z-]*$/.test(page)) add(`src/pages/${aliases[page] || page}.tsx`);
}

async function start() {
  const initial = JSON.parse(document.getElementById('antdData')?.textContent || '{}');
  primeCreationConfiguration(initial);
  const response = await fetch('/static/antd/manifest.json' + new URL(import.meta.url).search, { cache: 'no-store', credentials: 'same-origin' });
  if (!response.ok) throw new Error('无法读取界面资源清单');
  const manifest = await response.json();
  const entry = manifest['src/main.tsx']?.file;
  if (typeof entry !== 'string' || !/^app-[\w-]+\.js$/.test(entry)) throw new Error('界面资源清单无效');
  preloadModules(manifest, initial.page || '');
  await import(/* @vite-ignore */ `/static/antd/${entry}`);
}

start().catch(() => {
  discardInitialCreationConfiguration();
  const root = document.getElementById('antdRoot');
  if (!root) return;
  const status = document.createElement('p');
  status.setAttribute('role', 'alert');
  status.textContent = '界面资源加载失败，请刷新页面后重试。';
  const refresh = document.createElement('button');
  refresh.type = 'button';
  refresh.textContent = '刷新页面';
  refresh.addEventListener('click', () => location.reload());
  root.replaceChildren(status, refresh);
});
