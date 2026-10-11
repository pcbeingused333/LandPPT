import { Alert, Avatar, Card, Empty, Tag } from 'antd';
import { ArrowUpOutlined } from '@ant-design/icons';
import type { ApiData } from '../api';
import { safeWebURL } from '../forms';

export default function SponsorThanks({ data }: { data: ApiData }) {
  const sponsors: ApiData[] = data.sponsors || [];
  return <div className="sponsor-thanks-page settings-stack">
    <div className="page-heading"><div><h1>赞助感谢</h1><p>感谢每一位支持 LandPPT 持续迭代与维护的人。</p></div></div>
    {data.previewMode && data.user?.is_admin && <Alert type="warning" title="管理员预览：当前赞助感谢页尚未公开。" />}
    {sponsors.length ? <section className="sponsor-thanks-grid" aria-label="赞助名单">{sponsors.map((sponsor, index) => <Card size="small" key={index} className="sponsor-thanks-card">
      <div className="community-sponsor-identity"><Avatar size={44} src={safeWebURL(sponsor.avatar_url)}>{String(sponsor.nickname).slice(0, 1)}</Avatar><div><h2>{sponsor.nickname}</h2>{sponsor.amount && <span className="subtle">{sponsor.amount}</span>}</div></div>
      <p>{sponsor.bio || '感谢你的支持。'}</p>{sponsor.note && <Tag>{sponsor.note}</Tag>}
      {safeWebURL(sponsor.link_url) && <a className="sponsor-thanks-link" href={safeWebURL(sponsor.link_url)} target="_blank" rel="noopener noreferrer">访问主页 <ArrowUpOutlined rotate={45} aria-hidden /></a>}
    </Card>)}</section> : <Card size="small"><Empty description="赞助感谢页已开启，暂无赞助信息。" /></Card>}
  </div>;
}
