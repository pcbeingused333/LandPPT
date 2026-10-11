import { Button, Card, Space, Tag } from 'antd';
import { ArrowRightOutlined, FileTextOutlined, SettingOutlined, AppstoreOutlined, PictureOutlined } from '@ant-design/icons';
import type { ApiData } from '../api';

const providers: Record<string, string> = { landppt: 'LandPPT', openai: 'OpenAI', anthropic: 'Anthropic Claude', google: 'Google Gemini', gemini: 'Google Gemini', ollama: 'Ollama' };
const steps = [
  ['输入主题', '描述需求，也可以添加文件或网页资料。'],
  ['确认内容', '检查大纲，选择模板包或自由设计。'],
  ['编辑与导出', '调整每页内容，预览并导出演示文稿。'],
];

export default function Home({ data }: { data: ApiData }) {
  const provider = typeof data.aiProvider === 'string' ? data.aiProvider : '';
  return <div className="home-page">
    <Card className="home-intro" size="small">
      <div className="home-intro-copy"><span className="home-eyebrow">LANDPPT · AI 演示文稿</span><h1>创建你的演示文稿</h1><p>输入主题与需求，让 AI 帮你组织内容、设计页面。你可以在生成后继续编辑。</p>
        <Space wrap><Button type="primary" href="/create" icon={<ArrowRightOutlined aria-hidden />}>开始创建 PPT</Button><Button href="/dashboard">打开工作台</Button></Space>
      </div>
      <ol className="home-steps" aria-label="创建流程">{steps.map(([title, description], index) => <li key={title}><span className="home-step-number" aria-hidden>{String(index + 1).padStart(2, '0')}</span><div><h2>{title}</h2><p>{description}</p></div></li>)}</ol>
    </Card>
    {provider && <section className="home-provider" aria-label="当前 AI 配置"><span>当前 AI 提供者 <Tag>{providers[provider] || provider}</Tag></span><Button type="text" href="/ai-config" icon={<SettingOutlined aria-hidden />}>系统配置</Button></section>}
    <section aria-labelledby="homeShortcuts"><div className="section-heading"><h2 id="homeShortcuts">常用入口</h2><span className="subtle">内容、模板与素材</span></div><div className="home-shortcuts">{[
      { title: '项目管理', description: '查看项目、生成进度与已有演示文稿。', href: '/projects', icon: <FileTextOutlined aria-hidden /> },
      { title: '模板库', description: '选择演示风格，管理可复用的模板包。', href: '/global-master-templates', icon: <AppstoreOutlined aria-hidden /> },
      { title: '本地图床', description: '上传和管理演示文稿需要的图片素材。', href: '/image-gallery', icon: <PictureOutlined aria-hidden /> },
    ].map(item => <a className="home-shortcut" href={item.href} key={item.href}><span className="home-shortcut-icon">{item.icon}</span><div><h3>{item.title}</h3><p>{item.description}</p></div><ArrowRightOutlined aria-hidden /></a>)}</div></section>
  </div>;
}
