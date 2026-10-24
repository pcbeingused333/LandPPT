import { lazy, Suspense, Component, useMemo, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { App, ConfigProvider, Result, Button } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { landpptTheme } from './theme';
import { NavigationPending, Shell, type ShellData } from './shell';
import { useSectionNavigation, type SectionLoaders } from './navigation';
import { CreationDraftProvider } from './components/creation-draft';
import { EditorStartup } from './components/editor-startup';
import '../../src/landppt/web/static/css/shared/design-tokens.css';
import './styles.css';
import './workspace.css';

const sectionLoaders: SectionLoaders = {
  dashboard: () => import('./pages/dashboard'), settings: () => import('./pages/settings'), projects: () => import('./pages/projects'),
  'image-gallery': () => import('./pages/image-gallery'), templates: () => import('./pages/templates'),
  'create-project': () => import('./pages/create-project'), home: () => import('./pages/home'),
  'project-detail': () => import('./pages/project-detail'), profile: () => import('./pages/profile'), credits: () => import('./pages/credits'),
  research: () => import('./pages/research'), 'image-generation': () => import('./pages/image-generation'), 'sponsor-thanks': () => import('./pages/sponsor-thanks'),
  'admin-settings': () => import('./pages/admin-settings'), 'admin-users': () => import('./pages/admin-users'),
  'admin-credits': () => import('./pages/admin-credits'), 'admin-community': () => import('./pages/admin-community'),
  'admin-ai-providers': () => import('./pages/admin-ai-providers'),
};
const Dashboard = lazy(sectionLoaders.dashboard);
const Settings = lazy(sectionLoaders.settings);
const Projects = lazy(sectionLoaders.projects);
const ProjectDetail = lazy(sectionLoaders['project-detail']);
const Profile = lazy(sectionLoaders.profile);
const Credits = lazy(sectionLoaders.credits);
const Auth = lazy(() => import('./pages/auth'));
const AdminSettings = lazy(sectionLoaders['admin-settings']);
const AdminUsers = lazy(sectionLoaders['admin-users']);
const AdminCredits = lazy(sectionLoaders['admin-credits']);
const AdminCommunity = lazy(sectionLoaders['admin-community']);
const AdminAIProviders = lazy(sectionLoaders['admin-ai-providers']);
const SponsorThanks = lazy(sectionLoaders['sponsor-thanks']);
const ImageGallery = lazy(sectionLoaders['image-gallery']);
const ImageGeneration = lazy(sectionLoaders['image-generation']);
const Templates = lazy(sectionLoaders.templates);
const CreateProject = lazy(sectionLoaders['create-project']);
const Research = lazy(sectionLoaders.research);
const Home = lazy(sectionLoaders.home);
const GeneratorChrome = lazy(() => import('./pages/generator-chrome'));
const Presentation = lazy(() => import('./pages/presentation'));
const Todo = lazy(() => import('./pages/todo'));
const SlidesEditor = lazy(() => import('./pages/slides-editor'));
const ErrorPage = lazy(() => import('./pages/error'));
const pages = { dashboard: Dashboard, settings: Settings, projects: Projects, 'project-detail': ProjectDetail, profile: Profile, credits: Credits, auth: Auth, 'admin-settings': AdminSettings, 'admin-users': AdminUsers, 'admin-credits': AdminCredits, 'admin-community': AdminCommunity, 'admin-ai-providers': AdminAIProviders, 'sponsor-thanks': SponsorThanks, 'image-gallery': ImageGallery, 'image-generation': ImageGeneration, templates: Templates, 'template-selection': Templates, 'create-project': CreateProject, research: Research };

class PageBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed ? <Result status="error" title="页面加载失败" subTitle="请刷新页面后重试。" extra={<Button onClick={() => location.reload()}>刷新页面</Button>} /> : this.props.children;
  }
}

const root = document.getElementById('antdRoot');
function LandPPT({ initial }: { initial: ShellData & Record<string, any> }) {
  const { view, pending } = useSectionNavigation(initial, sectionLoaders);
  const data = view.data as typeof initial;
  const page = useMemo(() => {
    const Page = view.Page || (data.page === 'error' ? ErrorPage : data.page === 'slides-editor' ? SlidesEditor : data.page === 'home' ? Home : data.page === 'generator-workspace' ? GeneratorChrome : data.page === 'presentation' ? Presentation : data.page === 'todo' ? Todo : pages[data.page as keyof typeof pages]);
    return <PageBoundary key={view.key}><Suspense fallback={data.page === 'slides-editor' ? <EditorStartup /> : <div className="page-loading page-placeholder" role="status" aria-label="正在打开页面"><span /><span /><span /></div>}>
      {Page ? <Page data={data} /> : <Result status="404" title="页面不存在" extra={<Button href="/dashboard">返回首页</Button>} />}
    </Suspense></PageBoundary>;
  }, [view]);
  return <CreationDraftProvider key={`${data.user?.username || 'guest'}:${!!data.user?.is_admin}`}><NavigationPending.Provider value={pending}>{data.page === 'presentation' ? page : <Shell data={data}>{page}</Shell>}</NavigationPending.Provider></CreationDraftProvider>;
}
if (root) {
  const initial = JSON.parse(document.getElementById('antdData')!.textContent!) as ShellData & Record<string, any>;
  createRoot(root).render(<ConfigProvider locale={zhCN} theme={landpptTheme} button={{ autoInsertSpace: false }}><App><LandPPT initial={initial} /></App></ConfigProvider>);
}
