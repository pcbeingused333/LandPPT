import { useEffect, useState } from 'react';
import { Button, Empty, Pagination, Select, Space } from 'antd';
import { PlusOutlined, DashboardOutlined } from '@ant-design/icons';
import { ProjectCollection, projectStates, useProjectActions, type Project } from '../components/projects';
import type { ApiData } from '../api';

export default function Projects({ data }: { data: ApiData }) {
  const [projects, setProjects] = useState<Project[]>(data.projects);
  const { actions, renameDialog } = useProjectActions((id, title) => setProjects(previous => previous.map(project => project.project_id === id ? { ...project, title } : project)));
  function navigate(page: number, status = data.statusFilter || '') {
    const url = new URL(location.href);
    if (status) url.searchParams.set('status', status); else url.searchParams.delete('status');
    if (page > 1) url.searchParams.set('page', String(page)); else url.searchParams.delete('page');
    location.href = url.toString();
  }
  useEffect(() => {
    if (!projects.some(project => project.status === 'in_progress')) return;
    const timer = setInterval(() => {
      if (!document.hidden && !document.querySelector('.ant-modal-wrap:not([style*="display: none"])')) location.reload();
    }, 30000);
    return () => clearInterval(timer);
  }, [projects]);
  return <div className="projects-page">
    <div className="page-heading dashboard-header"><div><h1>项目列表</h1><p>管理您的所有 PPT 项目</p></div><Space><Button type="primary" href="/scenarios" icon={<PlusOutlined aria-hidden />}>创建项目</Button><Button href="/dashboard" icon={<DashboardOutlined aria-hidden />}>仪表板</Button></Space></div>
    <div className="projects-toolbar"><label htmlFor="statusFilter">状态筛选</label><Select id="statusFilter" value={data.statusFilter || ''} onChange={status => navigate(1, status)} options={[{ value: '', label: '全部状态' }, ...Object.entries(projectStates).map(([value, [label]]) => ({ value, label }))]} /><span className="subtle">共 {data.total} 个项目</span></div>
    <ProjectCollection projects={projects} actions={actions} empty={<Empty description={data.statusFilter ? '没有符合当前状态的项目' : '暂无项目'}><Space><Button type="primary" href="/scenarios">创建项目</Button>{data.statusFilter && <Button href="/projects">查看全部</Button>}</Space></Empty>} />
    <div className="projects-pagination"><Pagination current={data.currentPage} pageSize={data.pageSize} total={data.total} showSizeChanger={false} showLessItems onChange={page => navigate(page)} /><span className="subtle">第 {data.currentPage} 页 · 共 {Math.max(1, Math.ceil(data.total / data.pageSize))} 页</span></div>
    {renameDialog}
  </div>;
}
