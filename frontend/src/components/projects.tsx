import { useRef, useState, type ReactNode } from 'react';
import { App, Button, Card, Empty, Form, Input, Modal, Progress, Space, Table, Tag, Tooltip } from 'antd';
import { EyeOutlined, EditOutlined, FullscreenOutlined, CopyOutlined, DeleteOutlined, FormOutlined, UnorderedListOutlined } from '@ant-design/icons';
import { request } from '../api';
import { modalFocus } from './modal-focus';
import { navigatePage } from '../navigation';

export interface Project {
  project_id: string; title: string; topic?: string; scenario: string; updated: string; status: string; progress: number | null;
}
export const projectStates: Record<string, [string, string]> = { completed: ['已完成', 'success'], in_progress: ['进行中', 'default'], draft: ['草稿', 'warning'], archived: ['已归档', 'default'] };
export const projectPath = (project: Pick<Project, 'project_id'>) => `/projects/${encodeURIComponent(project.project_id)}`;
export function ProjectStatus({ project }: { project: Project }) {
  const state = projectStates[project.status] || ['异常状态', 'error'];
  return <div className="project-status"><Tag color={state[1]}>{state[0]}</Tag>{project.status === 'in_progress' && project.progress != null && <Progress size="small" percent={project.progress} />}</div>;
}

export function useProjectActions(onRename: (id: string, title: string) => void) {
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
  return { actions, renameDialog };
}

export function ProjectCollection({ projects, actions, empty }: { projects: Project[]; actions: (project: Project) => ReactNode; empty?: ReactNode }) {
  const placeholder = empty || <Empty description="暂无项目"><Button href="/scenarios">创建项目</Button></Empty>;
  return <>
    <div className="desktop-projects"><Table<Project> size="small" rowKey="project_id" dataSource={projects} pagination={false} locale={{ emptyText: placeholder }} columns={[
      { title: '项目', render: (_, project) => <div className="project-info"><a href={projectPath(project)} className="project-title" title={project.title}>{project.title}</a>{project.topic && <span className="project-topic subtle" title={project.topic}>{project.topic}</span>}<span className="subtle">场景：{project.scenario}</span></div> },
      { title: '状态', width: 140, render: (_, project) => <ProjectStatus project={project} /> },
      { title: '更新', dataIndex: 'updated', width: 130 },
      { title: '操作', width: 210, render: (_, project) => actions(project) },
    ]} /></div>
    <div className="mobile-projects">{projects.length ? projects.map(project => <Card size="small" key={project.project_id}><a href={projectPath(project)} className="project-title">{project.title}</a>{project.topic && <p className="project-topic subtle">{project.topic}</p>}<div className="mobile-project-meta"><ProjectStatus project={project} /><span className="subtle">{project.updated}</span></div><span className="subtle">场景：{project.scenario}</span>{actions(project)}</Card>) : placeholder}</div>
  </>;
}
