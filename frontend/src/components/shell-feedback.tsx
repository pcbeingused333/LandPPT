import { Alert, Button, Drawer, Empty, Space, Spin, Tag } from 'antd';
import type { ApiData } from '../api';

export function SiteAnnouncement({ notice }: { notice?: ApiData }) {
  if (!notice?.active || (!notice.title && !notice.message)) return null;
  const type = notice.level === 'danger' ? 'error' : ['success', 'warning', 'error'].includes(notice.level) ? notice.level : 'info';
  return <Alert className="app-announcement" showIcon type={type} title={notice.title} description={notice.message} />;
}

export function NotificationDrawer({ open, state, center }: { open: boolean; state: ApiData; center: any }) {
  const items: ApiData[] = state.notifications || [];
  return <Drawer open={open} title="通知" size={400} rootClassName="app-notification-drawer" getContainer={center?.panel || false} onClose={() => center?.close()}
    extra={<Button disabled={!center?.unreadCount || state.loading} onClick={() => center?.markAllRead()}>全部已读</Button>}>
    {state.loading ? <p role="status"><Spin size="small" /> 正在加载通知…</p> : state.error ? <Alert type="error" title={state.error} action={<Button onClick={() => center?.load()}>重试</Button>} /> : items.length ? <ul className="app-notifications">{items.map(item => <li key={item.id}>
      <Button className={`app-notification-item${item.is_read ? '' : ' is-unread'}`} onClick={event => center?.handleItemClick(item.id, item.link_url, event.currentTarget)}>
        <Space wrap><strong>{item.title}</strong>{!item.is_read && <Tag>未读</Tag>}</Space>
        {item.body && <span>{item.body}</span>}
        <small>{item.created_at ? new Date(Number(item.created_at) * 1000).toLocaleString('zh-CN', { hour12: false }) : ''}</small>
      </Button>
    </li>)}</ul> : <Empty description="暂无通知" />}
    {state.desktopAvailable && <Button className="app-desktop-notifications" onClick={() => center?.enableDesktop()}>开启浏览器桌面通知</Button>}
  </Drawer>;
}
