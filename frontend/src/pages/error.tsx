import { Alert, Button, Card, Result, Space } from 'antd';
import type { ApiData } from '../api';

export default function ErrorPage({ data }: { data: ApiData }) {
  return <section className="app-error-page">
    <Result status="error" title={<h1>页面处理失败</h1>} subTitle="当前页面暂时无法打开，请重试或返回项目列表。" extra={<Space wrap><Button onClick={() => history.back()}>返回上一页</Button><Button onClick={() => location.reload()}>重新加载</Button><Button type="primary" href="/home">返回首页</Button></Space>} />
    {data.error && <Alert type="error" title="错误详情" description={<pre>{data.error}</pre>} />}
    <Card size="small" title="常用入口"><Space wrap><Button href="/scenarios">创建 PPT</Button><Button href="/projects">项目列表</Button><Button href="/dashboard">首页</Button><Button href="/docs">API 文档</Button></Space></Card>
  </section>;
}
