import { useEffect, useRef, useState, type ReactNode } from 'react';
import { App, Button, Drawer, Dropdown, Space } from 'antd';
import { BellOutlined, MenuOutlined, UserOutlined, SettingOutlined, LogoutOutlined } from '@ant-design/icons';
import { modalFocus } from './components/modal-focus';

export interface ShellData {
  page: string;
  user: { username: string; is_admin?: boolean } | null;
  creditsEnabled: boolean;
}

declare global {
  interface Window {
    SiteNotice?: { loadPublicSettings(options: Record<string, string>): Promise<unknown> };
    NotificationCenter?: { mount(options: Record<string, string>): void };
  }
}

export function Shell({ data, children }: { data: ShellData; children: ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const authPage = data.page === 'auth';
  const menuTrigger = useRef<HTMLButtonElement>(null);
  const { modal } = App.useApp();
  useEffect(() => {
    window.SiteNotice?.loadPublicSettings({ noticeContainer: 'globalSiteNotice', sponsorLink: 'footerSponsorLink' });
    if (data.user) window.NotificationCenter?.mount({ bell: 'navNotificationBell', badge: 'navNotificationBadge' });
  }, [data.user]);
  const links = [
    ['首页', '/home'], ['工作台', '/dashboard'], ['项目', '/projects'], ['创建', '/create'],
    ['模板', '/global-master-templates'], ['图床', '/image-gallery'], ['配置', '/ai-config'],
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
  return <div className="app-shell">
    <a className="skip-link" href="#appMain">跳到主内容</a>
    <header className="app-header">
      <a className="app-brand" href="/">LandPPT<span>AI 演示文稿</span></a>
      {!authPage && <div className="desktop-navigation">{navigation}</div>}
      {authPage ? <Button className="app-account" href="/home">返回首页</Button> : <Space size={8} className="app-account">
        {data.user ? <><Button type="text" id="navNotificationBell" aria-label="通知" icon={<BellOutlined aria-hidden />}><span id="navNotificationBadge" hidden>0</span></Button>
          <Dropdown menu={{ items: account }} trigger={['click']}><Button type="text" icon={<UserOutlined aria-hidden />} aria-label="账户菜单"><span className="account-name">{data.user.username}</span></Button></Dropdown></>
          : <Button href="/auth/login">登录</Button>}
        <Button ref={menuTrigger} className="mobile-menu" type="text" aria-label="菜单" aria-expanded={menuOpen} icon={<MenuOutlined aria-hidden />} onClick={() => setMenuOpen(true)} />
      </Space>}
    </header>
    <Drawer title="导航" open={menuOpen} onClose={() => setMenuOpen(false)} afterOpenChange={open => { if (!open) menuTrigger.current?.focus(); }} size={280}>
      {navigation}<nav aria-label="账户导航" className="app-nav account-nav">
        {data.user ? <><a href="/auth/profile">个人资料</a>{data.creditsEnabled && <a href="/credits">我的积分</a>}{data.user.is_admin && <a href="/admin">管理后台</a>}<Button type="text" onClick={logout}>退出登录</Button></>
          : <><a href="/auth/login">登录</a><a href="/auth/login?tab=register">注册</a></>}
      </nav>
    </Drawer>
    <div id="globalSiteNotice" hidden />
    <main id="appMain" tabIndex={-1} className={`app-main${authPage ? ' auth-main' : ''}`}>{children}</main>
    <footer className="app-footer">LandPPT · v0.3.3 <a href="https://github.com/sligter/LandPPT" target="_blank" rel="noreferrer">GitHub</a><a id="footerSponsorLink" className="is-hidden" href="/sponsors">赞助感谢</a><a href="mailto:support@landppt.com">商务合作</a></footer>
  </div>;
}
