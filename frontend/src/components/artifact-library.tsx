import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Card, Empty, Flex, Input, Pagination, Popover, Select, Space, Spin, Tag, Typography } from 'antd';
import { AudioOutlined, DownloadOutlined, FilePdfOutlined, FilePptOutlined, PlayCircleOutlined, ReloadOutlined, SearchOutlined, VideoCameraOutlined } from '@ant-design/icons';
import { request, type ApiData } from '../api';
import { fileSize } from './images';
import { ArtifactMediaPreview } from './artifact-media-preview';

const kinds = [{ value: '', label: '全部类型' }, { value: 'pdf', label: 'PDF' }, { value: 'pptx', label: 'PPTX' }, { value: 'audio', label: '讲解音频' }, { value: 'video', label: '讲解视频' }];
const icons = { pdf: FilePdfOutlined, pptx: FilePptOutlined, audio: AudioOutlined, video: VideoCameraOutlined };

export function ArtifactLibrary({ active, projectId: fixedProjectId }: { active: boolean; projectId?: string }) {
  const [files, setFiles] = useState<ApiData[]>([]), [total, setTotal] = useState(0), [page, setPage] = useState(1);
  const [category, setCategory] = useState(''), [search, setSearch] = useState(''), [query, setQuery] = useState(''), [sort, setSort] = useState('newest');
  const [projectId, setProjectId] = useState(() => fixedProjectId ?? (new URLSearchParams(location.search).get('project') || '')), [project, setProject] = useState<ApiData | null>(null);
  const [loading, setLoading] = useState(false), [error, setError] = useState(''), [reload, setReload] = useState(0);
  const [preview, setPreview] = useState<ApiData | null>(null);
  const previewTrigger = useRef<HTMLElement | null>(null);
  useEffect(() => { if (!active) setPreview(null); }, [active]);
  useEffect(() => { if (active) { const id = fixedProjectId ?? (new URLSearchParams(location.search).get('project') || ''); if (id !== projectId) { setProjectId(id); setProject(null); setPage(1); } } }, [active, fixedProjectId]);
  useEffect(() => { const timer = setTimeout(() => setQuery(search), 200); return () => clearTimeout(timer); }, [search]);
  useEffect(() => {
    if (!active || projectId !== (fixedProjectId ?? (new URLSearchParams(location.search).get('project') || ''))) return;
    const controller = new AbortController();
    setLoading(true); setError('');
    const params = new URLSearchParams({ page: String(page), per_page: '20', category, search: query, sort });
    if (projectId) params.set('project_id', projectId);
    request('/api/artifact-library?' + params, 'GET', undefined, controller.signal).then(result => {
      if (controller.signal.aborted) return;
      if (!Array.isArray(result.files) || !Number.isInteger(result.pagination?.total_count) || result.pagination.total_count < 0 || !Number.isInteger(result.pagination?.current_page) || result.pagination.current_page < 1 || result.pagination.current_page > Math.max(1, Math.ceil(result.pagination.total_count / 20))) throw new Error('文件列表数据不完整，请重试');
      setFiles(result.files); setTotal(result.pagination.total_count); setProject(result.project || null);
      if (result.pagination.current_page !== page) setPage(result.pagination.current_page);
    }).catch(reason => { if (!controller.signal.aborted) { setFiles([]); setTotal(0); setError(reason.message); } }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [active, page, category, query, sort, projectId, reload]);
  function clearProject() {
    setProjectId(''); setProject(null); setPage(1);
    const url = new URL(location.href); url.searchParams.delete('project'); history.replaceState(history.state, '', url);
  }
  const clear = () => { setSearch(''); setQuery(''); setCategory(''); setSort('newest'); setPage(1); };
  return <div className="artifact-library settings-stack">
    <div className="page-heading"><div><h1>导出文件</h1><p>文稿、音频和视频</p></div><Button href="/projects">打开项目</Button></div>
    <Flex align="center" gap={8} wrap><Typography.Text type="secondary">仅展示系统已保存的文件。</Typography.Text><Popover title="文件范围" trigger="click" content={<Typography.Paragraph style={{ maxWidth: 240, margin: 0 }}>客户端 PPTX 和 HTML 文件包不会自动入库，请在浏览器下载目录中查找。</Typography.Paragraph>}><Button type="link" size="small">文件范围</Button></Popover></Flex>
    {projectId && <Flex align="center" gap={8} className="artifact-library-scope"><Tag><Typography.Text ellipsis={{ tooltip: project?.title }}>项目：{project?.title || '当前项目'}</Typography.Text></Tag>{!fixedProjectId && <Button type="link" size="small" aria-label="查看所有项目文件" onClick={clearProject}>所有项目</Button>}</Flex>}
    <Card size="small"><div className="artifact-library-toolbar">
      <Input.Search aria-label="搜索导出文件" enterButton={<Button className="artifact-library-search-submit" aria-label="搜索导出文件" icon={<SearchOutlined aria-hidden />} />} placeholder="搜索文件名或项目名称" allowClear maxLength={200} value={search} onChange={event => { setSearch(event.target.value); setPage(1); }} onSearch={value => { setQuery(value); setPage(1); }} />
      <Select aria-label="导出文件类型" value={category} options={kinds} onChange={value => { setCategory(value); setPage(1); }} />
      <Select aria-label="导出文件排序" value={sort} options={[{ value: 'newest', label: '最新生成' }, { value: 'oldest', label: '最早生成' }, { value: 'largest', label: '较大优先' }]} onChange={value => { setSort(value); setPage(1); }} />
      <Button aria-label="刷新导出文件" loading={loading} icon={<ReloadOutlined aria-hidden />} onClick={() => setReload(value => value + 1)} />
    </div></Card>
    {error && <Alert showIcon type="error" title="导出文件加载失败" description={error} action={<Button onClick={() => setReload(value => value + 1)}>重试</Button>} />}
    {loading && <div role="status"><Spin size="small" /> 正在读取导出文件…</div>}
    <section aria-label="已保存的导出文件" aria-busy={loading} className="artifact-library-files">{files.map(file => {
      const Icon = icons[file.category as keyof typeof icons] || FilePptOutlined;
      return <Card size="small" key={file.id}><Flex align="flex-start" gap={12} wrap className="artifact-library-file">
        <Icon aria-hidden className="artifact-library-icon" />
        <div className="artifact-library-info"><Typography.Text strong ellipsis={{ tooltip: file.filename }}>{file.filename}</Typography.Text>
          <Flex gap={8} wrap align="center"><Tag>{file.category_label}</Tag><Typography.Text type="secondary">{typeof file.file_size === 'number' ? fileSize(file.file_size) : '大小未知'}</Typography.Text><Typography.Text type="secondary">{file.created_at ? new Date(file.created_at * 1000).toLocaleString('zh-CN', { hour12: false }) : '时间未知'}</Typography.Text></Flex>
          {file.project ? <Typography.Link className="artifact-library-project" href={`/projects/${encodeURIComponent(file.project.id)}`} title={file.project.title}>项目：{file.project.title}</Typography.Link> : <Typography.Text type="secondary">未关联项目</Typography.Text>}
          {file.expires_at && <Typography.Text type="secondary">有效至 {new Date(file.expires_at * 1000).toLocaleString('zh-CN', { hour12: false })}</Typography.Text>}
        </div>
        <Flex gap={8} className="artifact-library-file-actions">
          {(file.preview_kind === 'audio' || file.preview_kind === 'video') && <Button aria-label={`预览 ${file.filename}`} icon={<PlayCircleOutlined aria-hidden />} onClick={event => { previewTrigger.current = event.currentTarget; setPreview(file); }}>预览</Button>}
          <Button href={`/api/artifacts/${encodeURIComponent(file.id)}/download`} download aria-label={`下载 ${file.filename}`} icon={<DownloadOutlined aria-hidden />}>下载</Button>
        </Flex>
      </Flex></Card>;
    })}</section>
    {!loading && !error && !files.length && <Card size="small"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={query || category ? '没有匹配的导出文件' : '暂无已保存的导出文件'}>{query || category ? <Button onClick={clear}>清除筛选</Button> : <Button href="/projects">打开项目继续创作</Button>}</Empty></Card>}
    <Space className="projects-pagination"><Typography.Text type="secondary">共 {total} 个文件</Typography.Text><Pagination current={page} pageSize={20} total={total} showSizeChanger={false} showLessItems disabled={loading} onChange={setPage} /></Space>
    <ArtifactMediaPreview file={preview} close={() => setPreview(null)} afterClose={() => { if (active && previewTrigger.current?.isConnected) previewTrigger.current.focus({ preventScroll: true }); }} />
  </div>;
}
