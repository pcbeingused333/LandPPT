import { useEffect, useRef, useState, type ComponentType } from 'react';
import type { ApiData } from './api';

export const sectionPaths: Record<string, string> = {
  '/home': 'home', '/dashboard': 'dashboard', '/projects': 'projects',
  '/create': 'create-project', '/scenarios': 'create-project',
  '/global-master-templates': 'templates', '/image-gallery': 'image-gallery', '/ai-config': 'settings',
  '/auth/profile': 'profile', '/credits': 'credits', '/research': 'research',
  '/image-generation-test': 'image-generation', '/sponsors': 'sponsor-thanks',
  '/admin': 'admin-users', '/admin/users': 'admin-users', '/admin/smtp': 'admin-settings',
  '/admin/oauth': 'admin-settings', '/admin/credits': 'admin-credits', '/admin/community': 'admin-community',
  '/admin/ai-providers': 'admin-ai-providers',
};

function pageForPath(path: string) {
  return sectionPaths[path] || (/^\/projects\/[^/]+$/.test(path) ? 'project-detail' : undefined);
}

// Use the same authenticated navigation for programmatic list actions.
export function navigatePage(href: string) {
  const event = new CustomEvent('landppt:navigate', { detail: href, cancelable: true });
  if (document.dispatchEvent(event)) location.assign(href);
}
type LoadedPage = { default: ComponentType<{ data: ApiData }> };
export type SectionLoaders = Record<string, () => Promise<LoadedPage>>;
type View = { data: ApiData; key: number; Page?: LoadedPage['default']; scroll?: { x: number; y: number } };

function sectionURL(href: string) {
  try { const url = new URL(href, location.href); return url.origin === location.origin && pageForPath(url.pathname) ? url : null; }
  catch { return null; }
}

export function useSectionNavigation(initial: ApiData, loaders: SectionLoaders) {
  const [view, setView] = useState<View>({ data: initial, key: 0 });
  const [pending, setPending] = useState('');
  const active = useRef<AbortController | null>(null);
  const current = useRef(view); current.current = view;
  const enabled = Object.hasOwn(loaders, initial.page);

  useEffect(() => {
    if (!enabled) return;
    let disposed = false;
    const preload = (href: string) => {
      const url = sectionURL(href);
      if (url) void loaders[pageForPath(url.pathname)!]().catch(() => {});
    };
    const anchor = (event: Event) => (event.target instanceof Element ? event.target.closest<HTMLAnchorElement>('a[href]') : null);
    const warm = (event: Event) => { const link = anchor(event); if (link && !link.target && link.closest('.app-shell, .app-nav, .app-account-menu')) preload(link.href); };
    async function navigate(url: URL, pop = false) {
      active.current?.abort();
      const controller = new AbortController(); active.current = controller;
      setPending(url.pathname);
      preload(url.href);
      const scroll = pop ? history.state?.landpptScroll || { x: 0, y: 0 } : { x: 0, y: 0 };
      if (!pop) history.replaceState({ ...history.state, landpptScroll: { x: scrollX, y: scrollY } }, '', location.href);
      let fallback = url.href;
      try {
        // Fetch the existing authenticated route, never cache user page data.
        const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store', signal: controller.signal, headers: { Accept: 'text/html' } });
        if (response.url && new URL(response.url).origin === location.origin) fallback = response.url;
        const target = sectionURL(response.url || url.href);
        if (!response.ok || !target) throw new Error('Use server navigation');
        if (!response.redirected) target.hash = url.hash;
        const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
        const payload = doc.getElementById('antdData');
        if (!payload || !doc.getElementById('antdRoot')) throw new Error('Use server navigation');
        const data = JSON.parse(payload.textContent || '') as ApiData;
        const user = current.current.data.user;
        if (data.page !== pageForPath(target.pathname) || data.user?.username !== user?.username || !!data.user?.is_admin !== !!user?.is_admin) throw new Error('Use server navigation');
        const asset = (source: Document) => source.querySelector<HTMLLinkElement>('link[href*="/static/antd/app.css"]')?.getAttribute('href');
        if (asset(doc) !== asset(document)) throw new Error('Use updated server assets');
        const { default: Page } = await loaders[data.page]();
        if (disposed || controller.signal.aborted) return;
        for (const id of ['settingsBlueprint', 'communityBlueprint']) {
          const blueprint = doc.getElementById(id);
          document.getElementById(id)?.remove();
          if (blueprint) document.getElementById('antdRoot')!.before(document.importNode(blueprint, true));
        }
        document.getElementById('antdData')!.textContent = JSON.stringify(data);
        document.title = doc.title;
        if (!pop) history.pushState(null, '', target.href);
        else if (target.href !== location.href) history.replaceState(null, '', target.href);
        setView(previous => ({ data, Page, scroll, key: previous.key + 1 }));
      } catch {
        if (!disposed && !controller.signal.aborted) location.assign(fallback);
      } finally {
        if (!disposed && active.current === controller) { active.current = null; setPending(''); }
      }
    }
    const click = (event: MouseEvent) => {
      const link = anchor(event);
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || !link || !link.closest('.app-shell, nav.app-nav, .app-account-menu') || link.target || link.hasAttribute('download')) return;
      const url = sectionURL(link.href);
      if (!url || document.querySelector('.ant-modal-wrap:not([style*="display: none"])')) return;
      event.preventDefault();
      if (url.href === location.href) { active.current?.abort(); active.current = null; setPending(''); return; }
      void navigate(url);
    };
    const back = () => {
      const url = sectionURL(location.href);
      if (url) void navigate(url, true); else location.reload();
    };
    const requested = (event: Event) => {
      const url = sectionURL((event as CustomEvent<string>).detail);
      if (url) { event.preventDefault(); void navigate(url); }
    };
    document.addEventListener('landppt:navigate', requested);
    document.addEventListener('click', click);
    document.addEventListener('pointerover', warm);
    document.addEventListener('focusin', warm);
    window.addEventListener('popstate', back);
    // Warm code only, one module at a time when idle; leave API calls to page mount.
    const connection = (navigator as Navigator & { connection?: { saveData?: boolean; effectiveType?: string } }).connection;
    const queue = [...new Set([...Object.values(sectionPaths), 'project-detail'])].filter(page => page !== initial.page && (initial.user?.is_admin || !page.startsWith('admin-')));
    let timer: number | undefined;
    let idle: number | undefined;
    const warmNext = () => {
      if (disposed || document.hidden) return;
      if (active.current) { schedule(); return; }
      const page = queue.shift();
      if (page) void loaders[page]().catch(() => {}).finally(schedule);
    };
    function schedule() { if (!disposed && queue.length) timer = window.setTimeout(() => { if (typeof window.requestIdleCallback === 'function') idle = window.requestIdleCallback(warmNext); else warmNext(); }, 1000); }
    if (!connection?.saveData && !connection?.effectiveType?.includes('2g')) schedule();
    return () => {
      disposed = true; active.current?.abort(); window.clearTimeout(timer);
      if (idle !== undefined) window.cancelIdleCallback(idle);
      document.removeEventListener('click', click);
      document.removeEventListener('landppt:navigate', requested);
      document.removeEventListener('pointerover', warm);
      document.removeEventListener('focusin', warm);
      window.removeEventListener('popstate', back);
    };
  }, [enabled, initial.page, loaders]);

  useEffect(() => {
    if (!view.key) return;
    const frame = requestAnimationFrame(() => { window.scrollTo(view.scroll?.x || 0, view.scroll?.y || 0); document.getElementById('appMain')?.focus({ preventScroll: true }); });
    return () => cancelAnimationFrame(frame);
  }, [view.key]);
  return { view, pending };
}
