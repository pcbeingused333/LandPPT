import { useEffect, useRef, useState, type ReactNode } from 'react';
import { App, Button, Drawer, Dropdown, Space, Tooltip } from 'antd';
import { BellOutlined, MenuOutlined, UserOutlined, SettingOutlined, LogoutOutlined, GithubOutlined, MailOutlined, HeartOutlined } from '@ant-design/icons';
import { version } from '../package.json';
import { modalFocus } from './components/modal-focus';
import { NotificationDrawer, SiteAnnouncement } from './components/shell-feedback';
import type { ApiData } from './api';

export interface ShellData {
  page: string;
  user: { username: string; is_admin?: boolean } | null;
  creditsEnabled: boolean;
}

declare global {
  interface Window {
    NotificationCenter?: { mount(options: Record<string, unknown>): any };
  }
}

export function Shell({ data, children, pending = '' }: { data: ShellData; children: ReactNode; pending?: string }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const authPage = data.page === 'auth';
  const menuTrigger = useRef<HTMLButtonElement>(null);
  const { modal, message } = App.useApp();
  const [notice, setNotice] = useState<ApiData>();
  const [sponsorsEnabled, setSponsorsEnabled] = useState(false);
  const [notifications, setNotifications] = useState<ApiData>({});
  const [notificationOpen, setNotificationOpen] = useState(false);
  const center = useRef<any>(null);
  useEffect(() => {
    let disposed = false;
    let reading: AbortController | undefined;
    async function refresh() {
      reading?.abort();
      const controller = new AbortController(); reading = controller;
      try {
        const response = await fetch('/api/community/public-settings', { credentials: 'same-origin', cache: 'no-store', signal: controller.signal });
        if (!response.ok) return;
        const settings = await response.json();
        if (!disposed && !controller.signal.aborted) {
          setNotice(settings.site_notice);
          setSponsorsEnabled(settings.sponsor_page_enabled === true);
        }
      } catch { /* Retain the last known settings on transient failures. */ }
    }
    const visible = () => { if (document.visibilityState === 'visible') void refresh(); };
    void refresh();
    window.addEventListener('landppt:community-settings-saved', refresh);
    document.addEventListener('visibilitychange', visible);
    return () => {
      disposed = true; reading?.abort();
      window.removeEventListener('landppt:community-settings-saved', refresh);
      document.removeEventListener('visibilitychange', visible);
    };
  }, [data]);
  useEffect(() => {
    let disposed = false;
    if (data.user) {
      center.current = window.NotificationCenter?.mount({ bell: 'navNotificationBell', badge: 'navNotificationBadge', renderUI: (value: ApiData) => { if (!disposed) setNotifications(value); }, onOpenChange: (open: boolean) => { if (!disposed) setNotificationOpen(open); }, notifyUI: (type: 'error' | 'success' | 'warning', content: string) => { if (!disposed) message[type](content); } });
      if (center.current?.panel) { center.current.panel.classList.add('app-notification-host'); center.current.panel.setAttribute('role', 'presentation'); }
    }
    return () => { disposed = true; center.current?.dispose(); center.current = null; };
  }, [data.user?.username]);
  useEffect(() => { setMenuOpen(false); }, [data.page]);
  const links = [
    ['工作台', '/dashboard'], ['项目', '/projects'], ['模板', '/global-master-templates'], ['素材', '/image-gallery'],
  ];
  const current = (href: string) => location.pathname === href || (href === '/projects' && location.pathname.startsWith('/projects/'));
  const logout = () => modal.confirm({ title: '退出登录', content: '确定要退出登录吗？', okText: '退出', cancelText: '取消', modalRender: modalFocus, onOk: () => { location.href = '/auth/logout'; } });
  const navigation = <nav aria-label="主导航" className="app-nav">{links.map(([label, href]) => <a key={href} href={href} aria-current={current(href) ? 'page' : undefined}>{label}</a>)}</nav>;
  const account = data.user ? [
    { key: 'profile', label: <a href="/auth/profile">个人资料</a>, icon: <UserOutlined aria-hidden /> },
    ...(data.creditsEnabled ? [{ key: 'credits', label: <a href="/credits">我的积分</a> }] : []),
    ...(data.user.is_admin ? [{ key: 'admin', label: <a href="/admin">管理后台</a>, icon: <SettingOutlined aria-hidden /> }] : []),
    { key: 'logout', label: '退出登录', icon: <LogoutOutlined aria-hidden />, onClick: logout },
  ] : [];
  return <div className={`app-shell${data.page === 'home' ? ' home-shell' : ''}`}>
    <a className="skip-link" href="#appMain">跳到主内容</a>
    <header className="app-header">
      <a className="app-brand" href="/">LandPPT</a>
      {!authPage && <div className="desktop-navigation">{navigation}</div>}
      {authPage ? <Button className="app-account" href="/home">返回首页</Button> : <Space size={8} className="app-account">
        <Tooltip title="系统配置" trigger={['hover', 'focus']}><Button className="app-settings" type="text" href="/ai-config" aria-label="系统配置" icon={<SettingOutlined aria-hidden />} /></Tooltip>
        {data.user ? <><Button type="text" id="navNotificationBell" aria-label="通知" icon={<BellOutlined aria-hidden />}><span id="navNotificationBadge" hidden>0</span></Button>
          <Dropdown classNames={{ root: 'app-account-menu' }} menu={{ items: account }} trigger={['click']}><Button type="text" icon={<UserOutlined aria-hidden />} aria-label="账户菜单"><span className="account-name">{data.user.username}</span></Button></Dropdown></>
          : <Button href="/auth/login">登录</Button>}
        <Button ref={menuTrigger} className="mobile-menu" type="text" aria-label="菜单" aria-expanded={menuOpen} icon={<MenuOutlined aria-hidden />} onClick={() => setMenuOpen(true)} />
      </Space>}
    </header>
    {pending && <div className="navigation-progress" role="status" aria-label="正在打开页面" />}
    <Drawer title="导航" open={menuOpen} onClose={() => setMenuOpen(false)} afterOpenChange={open => { if (!open) menuTrigger.current?.focus(); }} size={280}>
      {navigation}<nav aria-label="辅助导航" className="app-nav account-nav"><a href="/create">创建 PPT</a><a href="/home">产品首页</a><a href="/ai-config">系统配置</a></nav><nav aria-label="账户导航" className="app-nav account-nav">
        {data.user ? <><a href="/auth/profile">个人资料</a>{data.creditsEnabled && <a href="/credits">我的积分</a>}{data.user.is_admin && <a href="/admin">管理后台</a>}<Button type="text" onClick={logout}>退出登录</Button></>
          : <><a href="/auth/login">登录</a><a href="/auth/login?tab=register">注册</a></>}
      </nav>
    </Drawer>
    <SiteAnnouncement notice={notice} />
    <NotificationDrawer open={notificationOpen} state={notifications} center={center.current} />
    <main id="appMain" tabIndex={-1} aria-busy={!!pending} className={`app-main${authPage ? ' auth-main' : ''}${data.page === 'home' ? ' home-main' : ''}`}>{children}</main>
    <footer className="app-footer"><span>LandPPT · v{version}</span><a href="/home">产品首页</a><Tooltip title="GitHub" trigger={['hover', 'focus']}><a className="app-footer-icon" aria-label="GitHub" href="https://github.com/sligter/LandPPT" target="_blank" rel="noreferrer"><GithubOutlined aria-hidden /></a></Tooltip>{(sponsorsEnabled || data.user?.is_admin) && <a id="footerSponsorLink" className="app-footer-sponsor" href="/sponsors"><HeartOutlined aria-hidden />{sponsorsEnabled ? '赞助感谢' : '赞助预览'}</a>}<Tooltip title="商务合作" trigger={['hover', 'focus']}><a className="app-footer-icon" aria-label="商务合作" href="mailto:support@landppt.com"><MailOutlined aria-hidden /></a></Tooltip></footer>
  </div>;
}
