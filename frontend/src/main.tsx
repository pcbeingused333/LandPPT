import { lazy, Suspense, Component, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { App, ConfigProvider, Result, Button, Spin } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { landpptTheme } from './theme';
import { Shell, type ShellData } from './shell';
import './styles.css';

const Dashboard = lazy(() => import('./pages/dashboard'));
const Settings = lazy(() => import('./pages/settings'));
const Projects = lazy(() => import('./pages/projects'));
const ProjectDetail = lazy(() => import('./pages/project-detail'));
const Profile = lazy(() => import('./pages/profile'));
const Credits = lazy(() => import('./pages/credits'));
const Auth = lazy(() => import('./pages/auth'));
const AdminSettings = lazy(() => import('./pages/admin-settings'));
const AdminUsers = lazy(() => import('./pages/admin-users'));
const AdminCredits = lazy(() => import('./pages/admin-credits'));
const AdminCommunity = lazy(() => import('./pages/admin-community'));
const SponsorThanks = lazy(() => import('./pages/sponsor-thanks'));
const ImageGallery = lazy(() => import('./pages/image-gallery'));
const ImageGeneration = lazy(() => import('./pages/image-generation'));
const Templates = lazy(() => import('./pages/templates'));
const CreateProject = lazy(() => import('./pages/create-project'));
const Research = lazy(() => import('./pages/research'));
const Home = lazy(() => import('./pages/home'));
const GeneratorChrome = lazy(() => import('./pages/generator-chrome'));
const Presentation = lazy(() => import('./pages/presentation'));
const pages = { dashboard: Dashboard, settings: Settings, projects: Projects, 'project-detail': ProjectDetail, profile: Profile, credits: Credits, auth: Auth, 'admin-settings': AdminSettings, 'admin-users': AdminUsers, 'admin-credits': AdminCredits, 'admin-community': AdminCommunity, 'sponsor-thanks': SponsorThanks, 'image-gallery': ImageGallery, 'image-generation': ImageGeneration, templates: Templates, 'template-selection': Templates, 'create-project': CreateProject, research: Research };

class PageBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed ? <Result status="error" title="页面加载失败" subTitle="请刷新页面后重试。" extra={<Button onClick={() => location.reload()}>刷新页面</Button>} /> : this.props.children;
  }
}

const root = document.getElementById('antdRoot');
if (root) {
  const data = JSON.parse(document.getElementById('antdData')!.textContent!) as ShellData & Record<string, any>;
  const Page = data.page === 'home' ? Home : data.page === 'generator-workspace' ? GeneratorChrome : data.page === 'presentation' ? Presentation : pages[data.page as keyof typeof pages];
  const page = <PageBoundary><Suspense fallback={<div className="page-loading" role="status"><Spin /> 正在加载…</div>}>
    {Page ? <Page data={data} /> : <Result status="404" title="页面不存在" extra={<Button href="/dashboard">返回工作台</Button>} />}
  </Suspense></PageBoundary>;
  createRoot(root).render(<ConfigProvider locale={zhCN} theme={landpptTheme} button={{ autoInsertSpace: false }}>
    <App>{data.page === 'generator-workspace' || data.page === 'presentation' ? page : <Shell data={data}>{page}</Shell>}</App>
  </ConfigProvider>);
}
