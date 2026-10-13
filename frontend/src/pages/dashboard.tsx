import { useState } from 'react';
import { Button, Empty, Progress, Space } from 'antd';
import { ArrowRightOutlined, FileTextOutlined, PlusOutlined, UnorderedListOutlined } from '@ant-design/icons';
import type { ApiData } from '../api';
import { progressPercent } from '../progress';
import { projectPath, ProjectStatus, useProjectActions, type Project } from '../components/projects';

const summaries = [['总项目数', '/projects'], ['已完成', '/projects?status=completed'], ['进行中', '/projects?status=in_progress'], ['草稿', '/projects?status=draft']];

export default function Dashboard({ data }: { data: ApiData }) {
  const [projects, setProjects] = useState<Project[]>(data.projects);
  const { actions, renameDialog } = useProjectActions((id, title) => setProjects(previous => previous.map(project => project.project_id === id ? { ...project, title } : project)));
  return <div id="dashboardRoot">
    <div className="page-heading dashboard-header"><div><h1>项目仪表板</h1><p>继续创作，或开始一份新的演示文稿</p></div><Space><Button type="primary" href="/scenarios" icon={<PlusOutlined aria-hidden />}>创建项目</Button><Button href="/projects" icon={<UnorderedListOutlined aria-hidden />}>所有项目</Button></Space></div>
    <nav className="stats-grid dashboard-summary" aria-label="项目概览">{summaries.map(([label, href], index) => <a href={href} className="stat-card dashboard-stat" key={label} aria-label={`${label} ${Number(data.stats[index] || 0).toLocaleString()}`}><span className="stat-title">{label}</span><strong className="stat-number">{Number(data.stats[index] || 0).toLocaleString()}</strong><ArrowRightOutlined aria-hidden className="stat-arrow" /></a>)}</nav>
    <div className={`dashboard-workspace${data.todos.length ? ' dashboard-workspace--with-tasks' : ''}`}>
      <section className="dashboard-recent" aria-labelledby="recentProjectsTitle">
        <div className="section-heading recent-projects-header"><h2 id="recentProjectsTitle">最近项目</h2><span className="subtle">按更新时间排序</span></div>
        <div className="dashboard-projects">{projects.length ? <ul>{projects.map(project => <li className="dashboard-project-item" key={project.project_id}>
          <span className="dashboard-file-icon"><FileTextOutlined aria-hidden /></span><div className="project-info"><a href={projectPath(project)} className="project-title" title={project.title}>{project.title}</a><span className="subtle">{project.scenario} · 更新于 {project.updated}</span></div><ProjectStatus project={project} />{actions(project)}
        </li>)}</ul> : <Empty image={<FileTextOutlined aria-hidden />} description={<><strong>还没有项目</strong><p className="subtle">输入主题，让 AI 帮您生成第一份演示文稿。</p></>}><Button type="primary" href="/scenarios">创建第一份演示文稿</Button></Empty>}</div>
      </section>
      {!!data.todos.length && <aside className="dashboard-tasks" aria-labelledby="dashboardTasksTitle"><div className="section-heading"><h2 id="dashboardTasksTitle">进行中的任务</h2><span className="subtle">{data.todos.length} 项</span></div><div className="dashboard-task-list">{data.todos.map((todo: ApiData) => <article key={todo.id}><a className="dashboard-task-title" href={`/projects/${encodeURIComponent(todo.id)}/todo`}>{todo.title}</a><Progress percent={progressPercent(todo.progress)} strokeColor="#111" /><p className="subtle">当前阶段：{todo.stage}</p><Button href={`/projects/${encodeURIComponent(todo.id)}/todo`} icon={<ArrowRightOutlined aria-hidden />}>查看进度</Button></article>)}</div></aside>}
    </div>
    {renameDialog}
  </div>;
}
