import { useState } from 'react';
import { Button, Card, ConfigProvider, Empty, Flex, Grid, Progress, Typography } from 'antd';
import { ArrowRightOutlined, FileTextOutlined } from '@ant-design/icons';
import type { ApiData } from '../api';
import { progressPercent } from '../progress';
import { projectPath, ProjectCover, ProjectStatus, useProjectActions, type Project } from '../components/projects';
import CreateComposer from '../components/create-composer';

const summaries = [['总项目数', '/projects'], ['已完成', '/projects?status=completed'], ['进行中', '/projects?status=in_progress'], ['草稿', '/projects?status=draft']];

export default function Dashboard({ data }: { data: ApiData }) {
  const [projects, setProjects] = useState<Project[]>(data.projects);
  const screens = Grid.useBreakpoint();
  const { actions, renameDialog } = useProjectActions((id, title) => setProjects(previous => previous.map(project => project.project_id === id ? { ...project, title } : project)));
  return <div id="dashboardRoot">
    <div className="page-heading dashboard-header"><h1>项目仪表板</h1>
      <nav className="dashboard-summary" aria-label="项目概览">{summaries.map(([label, href], index) => <Button className="dashboard-stat" key={label} href={href} aria-label={`${label} ${Number(data.stats[index] || 0).toLocaleString()}`}><span className="stat-title">{label}</span><Typography.Text strong className="stat-number">{Number(data.stats[index] || 0).toLocaleString()}</Typography.Text></Button>)}</nav>
    </div>
    <section className="dashboard-create" aria-labelledby="dashboardCreateTitle"><Typography.Title level={2} id="dashboardCreateTitle" className="dashboard-create-title">想把什么，变成一场好演示？</Typography.Title><Typography.Paragraph type="secondary" className="dashboard-create-intro">输入主题即可开始，资料和参数按需添加。</Typography.Paragraph><CreateComposer data={data} compact /></section>
    <div className={`dashboard-workspace${data.todos.length ? ' dashboard-workspace--with-tasks' : ''}`}>
      <section className="dashboard-recent" aria-labelledby="recentProjectsTitle">
        <div className="section-heading recent-projects-header"><h2 id="recentProjectsTitle">最近项目</h2><Button type="text" className="dashboard-all-projects" href="/projects">所有项目<ArrowRightOutlined aria-hidden /></Button></div>
        <div className="dashboard-projects">{projects.length ? <ul>{projects.map(project => <li className="dashboard-project-item" key={project.project_id}>
          <Card hoverable size="small" cover={<a className="project-cover-link" href={projectPath(project)} aria-label={`打开项目 ${project.title}`}><ProjectCover project={project} /></a>}>
            <Card.Meta title={<a href={projectPath(project)} className="project-title" title={project.title}>{project.title}</a>} description={`更新于 ${project.updated}`} />
            <Flex className="dashboard-project-footer" justify="space-between" align="center" gap={8}><ProjectStatus project={project} /><ConfigProvider componentSize={screens.md ? 'small' : undefined}>{actions(project)}</ConfigProvider></Flex>
          </Card>
        </li>)}</ul> : <Empty image={<FileTextOutlined aria-hidden />} description={<><strong>还没有项目</strong><p className="subtle">输入主题，让 AI 帮您生成第一份演示文稿。</p></>}><Button type="primary" href="/scenarios">创建第一份演示文稿</Button></Empty>}</div>
      </section>
      {!!data.todos.length && <aside className="dashboard-tasks" aria-labelledby="dashboardTasksTitle"><div className="section-heading"><h2 id="dashboardTasksTitle">进行中的任务</h2><span className="subtle">{data.todos.length} 项</span></div><div className="dashboard-task-list">{data.todos.map((todo: ApiData) => <article key={todo.id}><a className="dashboard-task-title" href={`/projects/${encodeURIComponent(todo.id)}/todo`}>{todo.title}</a><Progress percent={progressPercent(todo.progress)} strokeColor="#111" /><p className="subtle">当前阶段：{todo.stage}</p><Button href={`/projects/${encodeURIComponent(todo.id)}/todo`} icon={<ArrowRightOutlined aria-hidden />}>查看进度</Button></article>)}</div></aside>}
    </div>
    {renameDialog}
  </div>;
}
