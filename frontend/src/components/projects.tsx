import { useRef, useState, type ReactNode } from 'react';
import { App, Button, Card, Dropdown, Empty, Form, Image, Input, Modal, Progress, Space, Table, Tag, Tooltip } from 'antd';
import { EyeOutlined, EditOutlined, FileTextOutlined, FullscreenOutlined, CopyOutlined, DeleteOutlined, FormOutlined, UnorderedListOutlined, MoreOutlined, StarOutlined, StarFilled, PushpinOutlined, PushpinFilled } from '@ant-design/icons';
import { request } from '../api';
import { modalFocus } from './modal-focus';
import { navigatePage } from '../navigation';
import { progressPercent } from '../progress';

export interface Project {
  project_id: string; title: string; topic?: string; scenario: string; updated: string; status: string; progress: number | null; cover_url?: string | null;
  is_favorite?: boolean; is_pinned?: boolean;
}
export const projectStates: Record<string, [string, string]> = { completed: ['已完成', 'success'], in_progress: ['进行中', 'default'], draft: ['草稿', 'warning'], archived: ['已归档', 'default'] };
export const projectPath = (project: Pick<Project, 'project_id'>) => `/projects/${encodeURIComponent(project.project_id)}`;
const coverTones = 6;
export function ProjectTitleCover({ project }: { project: Project }) {
  const tone = [...project.project_id].reduce((sum, char) => (sum * 31 + char.charCodeAt(0)) >>> 0, 7) % coverTones;
  return <div className={`project-title-cover project-title-cover--${tone}`} aria-hidden="true"><FileTextOutlined className="project-cover-mark" /><strong>{project.title}</strong></div>;
}
export function ProjectCover({ project }: { project: Project }) {
  return project.cover_url ? <ProjectImageCover key={project.cover_url} project={project} /> : <ProjectTitleCover project={project} />;
}
function ProjectImageCover({ project }: { project: Project }) {
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  return <div className={`project-cover${loaded && !failed ? ' project-cover--loaded' : ''}`} aria-hidden="true">
    <ProjectTitleCover project={project} />
    {!failed && <Image className="project-cover-image" src={project.cover_url!} alt="" preview={false} loading="lazy" decoding="async" onLoad={() => setLoaded(true)} onError={() => setFailed(true)} />}
  </div>;
}
export function ProjectStatus({ project }: { project: Project }) {
  const state = projectStates[project.status] || ['异常状态', 'error'];
  return <div className="project-status"><Tag color={state[1]}>{state[0]}</Tag>{project.status === 'in_progress' && project.progress != null && <Progress size="small" percent={progressPercent(project.progress)} />}</div>;
}

export function ProjectLibraryTitle({ project, organize }: { project: Project; organize: (project: Project) => ReactNode }) {
  return <div className="project-library-title"><a href={projectPath(project)} className="project-title" title={project.title}>{project.title}</a><Space size={4}>
    {project.is_pinned && <Tooltip title="已置顶"><PushpinFilled aria-label="已置顶" /></Tooltip>}
    {project.is_favorite && <Tooltip title="已收藏"><StarFilled aria-label="已收藏" /></Tooltip>}
    {organize(project)}
  </Space></div>;
}

export function useProjectActions(onRename: (id: string, title: string) => void, onOrganized?: (id: string, flags: Pick<Project, 'is_favorite' | 'is_pinned'>) => Promise<void>) {
  const { message, modal } = App.useApp();
  const [rename, setRename] = useState<Project | null>(null);
  const [busy, setBusy] = useState(false);
  const locked = useRef(false);
  const confirming = useRef(false);
  const [form] = Form.useForm();
  async function saveName() {
    if (locked.current || !rename) return;
    let title: string;
    try { ({ title } = await form.validateFields()); } catch { return; }
    if (locked.current) return;
    locked.current = true; setBusy(true);
    try {
      const result = await request(`/api/projects/${encodeURIComponent(rename.project_id)}/rename`, 'PATCH', { title: title.trim() });
      if (result.status !== 'success') throw new Error(result.message || '重命名失败');
      onRename(rename.project_id, title.trim()); setRename(null); message.success('项目已重命名');
    } catch (error) { message.error((error as Error).message); }
    finally { locked.current = false; setBusy(false); }
  }
  async function duplicate(project: Project) {
    if (locked.current) return;
    locked.current = true; setBusy(true);
    try {
      const result = await request(`/api/projects/${encodeURIComponent(project.project_id)}/duplicate`, 'POST');
      if (result.status !== 'success' || !result.project_id) throw new Error('复制失败');
      navigatePage(`/projects/${encodeURIComponent(result.project_id)}`);
    } catch (error) { message.error((error as Error).message); locked.current = false; setBusy(false); }
  }
  function remove(project: Project) {
    if (confirming.current) return;
    confirming.current = true;
    modal.confirm({ title: '确认删除项目', content: <>将永久删除“{project.title}”及其相关数据，此操作不可撤销。</>, okText: '删除', cancelText: '取消', okButtonProps: { danger: true }, modalRender: modalFocus,
      afterClose: () => { confirming.current = false; },
      onOk: async () => {
        try { await request(`/api/database/projects/${encodeURIComponent(project.project_id)}`, 'DELETE'); location.reload(); }
        catch (error) { message.error((error as Error).message); throw error; }
      },
    });
  }
  async function organizeProject(project: Project, field: 'is_favorite' | 'is_pinned') {
    if (locked.current) return;
    locked.current = true; setBusy(true);
    try {
      const result = await request(`/api/projects/${encodeURIComponent(project.project_id)}/library-preferences`, 'PATCH', { [field]: !project[field] });
      if (result.status !== 'success' || typeof result.is_favorite !== 'boolean' || typeof result.is_pinned !== 'boolean') throw new Error('项目整理未保存，请重试');
      // The server orders/filters the entire library before paginating. Reload
      // authoritative rows and totals rather than sorting only this page.
      if (onOrganized) {
        await onOrganized(project.project_id, { is_favorite: result.is_favorite, is_pinned: result.is_pinned });
        locked.current = false; setBusy(false);
      } else location.reload();
    } catch (error) { message.error((error as Error).message); locked.current = false; setBusy(false); }
  }
  const organize = (project: Project) => <Dropdown trigger={['click']} menu={{ items: [
    { key: 'is_favorite', icon: project.is_favorite ? <StarFilled aria-hidden /> : <StarOutlined aria-hidden />, label: project.is_favorite ? '取消收藏' : '收藏项目', disabled: busy },
    { key: 'is_pinned', icon: project.is_pinned ? <PushpinFilled aria-hidden /> : <PushpinOutlined aria-hidden />, label: project.is_pinned ? '取消置顶' : '置顶项目', disabled: busy },
  ], onClick: ({ key }) => { if (key === 'is_favorite' || key === 'is_pinned') void organizeProject(project, key); } }}>
    <Button disabled={busy} type="text" aria-label="整理项目" title="收藏与置顶" icon={<MoreOutlined aria-hidden />} />
  </Dropdown>;
  const actions = (project: Project) => <Space size={2} className="project-actions">
    <Tooltip title="详情"><Button href={projectPath(project)} type="text" aria-label="详情" icon={<EyeOutlined aria-hidden />} /></Tooltip>
    {project.status === 'completed' && <><Tooltip title="编辑"><Button href={`${projectPath(project)}/edit`} type="text" aria-label="编辑" icon={<EditOutlined aria-hidden />} /></Tooltip><Tooltip title="预览"><Button href={`${projectPath(project)}/fullscreen`} target="_blank" rel="noopener" type="text" aria-label="预览" icon={<FullscreenOutlined aria-hidden />} /></Tooltip></>}
    {project.status === 'in_progress' && <Button href={`${projectPath(project)}/todo`} type="text" aria-label="查看进度" icon={<UnorderedListOutlined aria-hidden />} />}
    <Tooltip title="重命名"><Button disabled={busy} type="text" aria-label="重命名" icon={<FormOutlined aria-hidden />} onClick={() => { setRename(project); form.setFieldsValue({ title: project.title }); }} /></Tooltip>
    <Tooltip title="复制"><Button disabled={busy} type="text" aria-label="复制" icon={<CopyOutlined aria-hidden />} onClick={() => duplicate(project)} /></Tooltip>
    <Tooltip title="删除"><Button disabled={busy} danger type="text" aria-label="删除" icon={<DeleteOutlined aria-hidden />} onClick={() => remove(project)} /></Tooltip>
  </Space>;
  const renameDialog = <Modal title="重命名项目" modalRender={modalFocus} open={!!rename} onCancel={() => { if (!busy) setRename(null); }} onOk={saveName} confirmLoading={busy} okText="保存" cancelText="取消" destroyOnHidden>
    <Form form={form} layout="vertical" onFinish={saveName}><Form.Item name="title" label="项目名称" htmlFor="renameProjectTitle" rules={[{ required: true, whitespace: true, message: '项目名称不能为空' }, { max: 255, message: '项目名称不能超过 255 个字符' }]}><Input id="renameProjectTitle" autoFocus maxLength={255} /></Form.Item></Form>
  </Modal>;
  return { actions, organize, renameDialog };
}

function ProjectContext({ project }: { project: Project }) {
  const topic = project.topic?.trim();
  const showTopic = topic && project.title.trim() !== topic && project.title.trim() !== `${topic} - ${project.scenario}`;
  const showScenario = project.scenario && !['general', '通用', '通用场景'].includes(project.scenario);
  return <>{showTopic && <span className="project-topic subtle" title={topic}>{topic}</span>}{showScenario && <span className="subtle">场景：{project.scenario}</span>}</>;
}

export function ProjectCollection({ projects, actions, organize, empty }: { projects: Project[]; actions: (project: Project) => ReactNode; organize: (project: Project) => ReactNode; empty?: ReactNode }) {
  const [view, setView] = useState<'cards' | 'list'>('cards');
  const placeholder = empty || <Empty description="暂无项目"><Button href="/scenarios">创建项目</Button></Empty>;
  return <>
    <div className="project-view-switch" role="group" aria-label="项目显示方式"><Button aria-pressed={view === 'cards'} type={view === 'cards' ? 'primary' : 'default'} onClick={() => setView('cards')}>封面</Button><Button aria-pressed={view === 'list'} type={view === 'list' ? 'primary' : 'default'} onClick={() => setView('list')}>列表</Button></div>
    <div className={`project-collection project-collection--${view}`}>
    <div className="desktop-projects"><Table<Project> size="small" rowKey="project_id" dataSource={projects} pagination={false} locale={{ emptyText: placeholder }} columns={[
      { title: '项目', render: (_, project) => <div className="project-info"><ProjectLibraryTitle project={project} organize={organize} /><ProjectContext project={project} /></div> },
      { title: '状态', width: 140, render: (_, project) => <ProjectStatus project={project} /> },
      { title: '更新', dataIndex: 'updated', width: 130 },
      { title: '操作', width: 210, render: (_, project) => actions(project) },
    ]} /></div>
    <div className="mobile-projects">{projects.length ? projects.map(project => <Card className="project-library-card" size="small" key={project.project_id} cover={<a className="project-cover-link" href={projectPath(project)} aria-label={`打开项目 ${project.title}`}><ProjectCover project={project} /></a>}><ProjectLibraryTitle project={project} organize={organize} /><ProjectContext project={project} /><div className="mobile-project-meta"><ProjectStatus project={project} /><span className="subtle">{project.updated}</span></div>{actions(project)}</Card>) : placeholder}</div>
    </div>
  </>;
}
