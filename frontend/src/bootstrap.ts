// The small loader can be versioned independently. Shared page chunks import
// the hashed application entry, so there is only one React runtime/root URL.
async function start() {
  const response = await fetch('/static/antd/manifest.json' + new URL(import.meta.url).search, { cache: 'no-store', credentials: 'same-origin' });
  if (!response.ok) throw new Error('无法读取界面资源清单');
  const manifest = await response.json();
  const entry = manifest['src/main.tsx']?.file;
  if (typeof entry !== 'string' || !/^app-[\w-]+\.js$/.test(entry)) throw new Error('界面资源清单无效');
  await import(/* @vite-ignore */ `/static/antd/${entry}`);
}

start().catch(() => {
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
