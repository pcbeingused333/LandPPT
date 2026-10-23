import { useEffect, useState } from 'react';
import { Button, Empty, Input, Pagination, Select, Space, Tabs } from 'antd';
import { PlusOutlined, DashboardOutlined, SearchOutlined, CloseCircleFilled } from '@ant-design/icons';
import { ProjectCollection, projectStates, useProjectActions, type Project } from '../components/projects';
import type { ApiData } from '../api';
import { navigatePage } from '../navigation';

export default function Projects({ data }: { data: ApiData }) {
  const [projects, setProjects] = useState<Project[]>(data.projects);
  const [search, setSearch] = useState<string>(data.searchQuery || '');
  const { actions, organize, renameDialog } = useProjectActions((id, title) => setProjects(previous => previous.map(project => project.project_id === id ? { ...project, title } : project)));
  function navigate(page: number, status = data.statusFilter || '', query = data.searchQuery || '', favorite = !!data.favoriteFilter, sort = data.sortOrder || 'pinned') {
    const url = new URL(location.href);
    if (status) url.searchParams.set('status', status); else url.searchParams.delete('status');
    if (query.trim()) url.searchParams.set('search', query.trim()); else url.searchParams.delete('search');
    if (page > 1) url.searchParams.set('page', String(page)); else url.searchParams.delete('page');
    if (favorite) url.searchParams.set('favorite', 'true'); else url.searchParams.delete('favorite');
    if (sort !== 'pinned') url.searchParams.set('sort', sort); else url.searchParams.delete('sort');
    navigatePage(url.toString());
  }
  useEffect(() => {
    if (!projects.some(project => project.status === 'in_progress')) return;
    const timer = setInterval(() => {
      if (!document.hidden && !document.activeElement?.closest('.projects-toolbar') && !document.querySelector('.ant-modal-wrap:not([style*="display: none"])')) location.reload();
    }, 30000);
    return () => clearInterval(timer);
  }, [projects]);
  return <div className="projects-page">
    <div className="page-heading dashboard-header"><div><h1>项目列表</h1><p>管理您的所有 PPT 项目</p></div><Space><Button type="primary" href="/scenarios" icon={<PlusOutlined aria-hidden />}>创建项目</Button><Button href="/dashboard" icon={<DashboardOutlined aria-hidden />}>仪表板</Button></Space></div>
    <Tabs className="project-library-tabs" activeKey={data.favoriteFilter ? 'favorites' : 'all'} items={[{ key: 'all', label: '全部项目' }, { key: 'favorites', label: '我的收藏' }]} onChange={key => navigate(1, data.statusFilter || '', data.searchQuery || '', key === 'favorites')} />
    <div className="projects-toolbar"><Input.Search className="projects-search" role="searchbox" aria-label="搜索项目" placeholder="搜索标题、主题或项目 ID" value={search} onChange={event => setSearch(event.target.value)} allowClear={{ clearIcon: <CloseCircleFilled aria-label="清除搜索" /> }} enterButton={<Button aria-label="搜索" title="搜索" icon={<SearchOutlined aria-hidden />} />} onSearch={query => navigate(1, data.statusFilter || '', query)} /><div className="projects-status-filter"><label htmlFor="statusFilter">状态筛选</label><Select id="statusFilter" value={data.statusFilter || ''} onChange={status => navigate(1, status)} options={[{ value: '', label: '全部状态' }, ...Object.entries(projectStates).map(([value, [label]]) => ({ value, label }))]} /></div><div className="projects-sort-filter"><label htmlFor="projectSort">排序</label><Select id="projectSort" value={data.sortOrder || 'pinned'} onChange={sort => navigate(1, data.statusFilter || '', data.searchQuery || '', !!data.favoriteFilter, sort)} options={[{ value: 'pinned', label: '置顶优先' }, { value: 'updated', label: '最近更新' }]} /></div><span className="subtle">共 {data.total} 个项目</span></div>
    <ProjectCollection projects={projects} actions={actions} organize={organize} empty={<Empty description={data.searchQuery ? '没有找到匹配的项目' : data.statusFilter ? '没有符合当前状态的项目' : data.favoriteFilter ? '还没有收藏的项目' : '暂无项目'}><Space><Button type="primary" href="/scenarios">创建项目</Button>{(data.statusFilter || data.searchQuery || data.favoriteFilter) && <Button href="/projects">查看全部</Button>}</Space></Empty>} />
    <div className="projects-pagination"><Pagination current={data.currentPage} pageSize={data.pageSize} total={data.total} showSizeChanger={false} showLessItems onChange={page => navigate(page)} /><span className="subtle">第 {data.currentPage} 页 · 共 {Math.max(1, Math.ceil(data.total / data.pageSize))} 页</span></div>
    {renameDialog}
  </div>;
}
