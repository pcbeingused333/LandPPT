import { useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Card, Drawer, Flex, Form, Input, Select, Skeleton, Space, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { request, type ApiData } from '../api';
import { modalFocus } from './modal-focus';
import { nativeSelectIsOpen } from './native-controls';

export type BatchPage = { key: string; index: number; slideId: string | null; title: string };
type Row = BatchPage & { document: ApiData; title: string; slideType: string };
const types = [{ value: 'title', label: '封面' }, { value: 'content', label: '内容页' }, { value: 'transition', label: '章节过渡页' }, { value: 'conclusion', label: '总结页' }];

export function EditorOutlineBatch({ open, projectId, pages, origin, onClose, onSaved }: {
  open: boolean; projectId: string; pages: BatchPage[]; origin: HTMLElement | null; onClose: () => void; onSaved: (items: { key: string; document: ApiData }[]) => void;
}) {
  const { modal, message } = App.useApp();
  const [base, setBase] = useState<Row[]>([]), [rows, setRows] = useState<Row[]>([]);
  const [revision, setRevision] = useState(''), [loading, setLoading] = useState(false), [saving, setSaving] = useState(false);
  const [error, setError] = useState(''), [editable, setEditable] = useState(false), [reload, setReload] = useState(0);
  const [prefix, setPrefix] = useState(''), [uniformType, setUniformType] = useState<string>();
  const locked = useRef(false);
  const problem = useRef<HTMLDivElement>(null);
  const endpoint = `/api/projects/${encodeURIComponent(projectId)}/editor-outline-batch`;
  const changed = rows.filter(row => { const original = base.find(item => item.key === row.key); return original && (row.title !== original.title || row.slideType !== original.slideType); });
  const dirty = changed.length > 0;
  useEffect(() => {
    if (!open || loading || !error) return;
    const body = problem.current?.closest<HTMLElement>('.ant-drawer-body');
    if (body) body.scrollTop = 0;
    problem.current?.focus({ preventScroll: true });
  }, [open, loading, error]);
  useEffect(() => {
    if (!open || !pages.length) return;
    const controller = new AbortController();
    setLoading(true); setError(''); setRows([]); setBase([]); setRevision(''); setPrefix(''); setUniformType(undefined);
    const params = new URLSearchParams(); pages.forEach(page => params.append('indices', String(page.index)));
    request(`${endpoint}?${params}`, 'GET', undefined, controller.signal).then(result => {
      if (controller.signal.aborted) return;
      if (typeof result.project_revision !== 'string' || !Array.isArray(result.pages) || result.pages.length !== pages.length) throw new Error('批量文稿数据不完整，请重试读取');
      const loaded = pages.map(page => {
        const document = result.pages.find((item: ApiData) => item.slide_index === page.index);
        if (!document?.outline || typeof document.outline_revision !== 'string' || page.slideId && document.slide_id !== page.slideId) throw new Error('页面顺序已改变，请刷新编辑器后重试');
        return { ...page, slideId: document.slide_id, document, title: String(document.outline.title || page.title || ''), slideType: document.outline.slide_type || document.outline.type || 'content' };
      });
      setBase(loaded); setRows(loaded); setRevision(result.project_revision); setEditable(result.editable === true);
    }).catch(reason => { if (!controller.signal.aborted) setError(reason.message); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [open, pages, endpoint, reload]);
  useEffect(() => {
    if (!open) return;
    const warn = (event: BeforeUnloadEvent) => { if (dirty || saving) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn);
  }, [open, dirty, saving]);
  function confirmDiscard(title: string, action: () => void) {
    if (!dirty) { action(); return; }
    modal.confirm({ title, content: '本次未保存的批量修改会被丢弃。', okText: '放弃修改', cancelText: '继续编辑', modalRender: modalFocus, onOk: action });
  }
  function close() { if (!locked.current) confirmDiscard('放弃本次批量修改？', onClose); }
  function setRow(key: string, values: Partial<Row>) { setRows(current => current.map(row => row.key === key ? { ...row, ...values } : row)); }
  function addPrefix() {
    if (!prefix || saving || !editable) return;
    if (rows.some(row => (prefix + row.title).length > 255)) { setError('添加前缀后有标题超过 255 个字符，请缩短前缀或标题'); return; }
    setRows(current => current.map(row => ({ ...row, title: prefix + row.title })));
  }
  async function save() {
    if (locked.current || !editable || loading || !revision || !changed.length) return;
    const empty = changed.find(row => !row.title.trim());
    if (empty) { setError(`请填写第 ${empty.index + 1} 页标题`); return; }
    locked.current = true; setSaving(true); setError('');
    try {
      const result = await request(endpoint, 'PATCH', { project_revision: revision, pages: changed.map(row => {
        const original = base.find(item => item.key === row.key)!;
        return { slide_index: row.index, slide_id: row.slideId, revision: row.document.outline_revision, changes: {
          ...(row.title !== original.title ? { title: row.title } : {}), ...(row.slideType !== original.slideType ? { slide_type: row.slideType } : {}),
        } };
      }) });
      if (!Array.isArray(result.pages) || result.pages.length !== changed.length || new Set(result.pages.map((document: ApiData) => document.slide_index)).size !== changed.length || result.pages.some((document: ApiData) => !document.outline || typeof document.outline_revision !== 'string' || !changed.some(row => row.index === document.slide_index && row.slideId === document.slide_id))) throw new Error('服务器已响应，请重新读取核对保存结果；当前草稿已保留');
      onSaved(result.pages.map((document: ApiData) => ({ key: changed.find(row => row.index === document.slide_index)!.key, document })));
      setBase(rows); onClose(); void message.success(`已保存 ${changed.length} 页大纲修改`);
    } catch (reason) { setError((reason as Error).message); }
    finally { locked.current = false; setSaving(false); }
  }
  return <Drawer title={`批量编辑大纲 · ${pages.length} 页`} open={open} size={720} styles={{ wrapper: { maxWidth: '100vw' } }}
    closable={!saving} maskClosable={!saving} keyboard={!saving} onClose={close} afterOpenChange={value => { if (!value && origin?.isConnected) origin.focus(); }}
    drawerRender={node => <div style={{ height: '100%' }} onKeyDown={event => { event.stopPropagation(); if (event.key === 'Escape' && !nativeSelectIsOpen(event.target)) { event.preventDefault(); close(); } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); void save(); } }}>{modalFocus(node, { height: '100%' })}</div>}
    footer={<Flex justify="space-between" align="center" gap={8} wrap><Typography.Text type="secondary" role="status">{changed.length} 页有修改</Typography.Text><Space><Button disabled={saving} onClick={close}>取消</Button><Button type="primary" loading={saving} disabled={loading || !editable || !dirty} onClick={() => void save()}>保存 {changed.length} 页修改</Button></Space></Flex>}>
    <Space orientation="vertical" size="middle" className="editor-outline-batch-form">
      <Alert showIcon type="info" title="保存只更新大纲，现有页面不会自动重绘。" description="有页面冲突时整批不保存，修改草稿会保留。" />
      {loading ? <Skeleton active paragraph={{ rows: 8 }} /> : <>
        {error && <div ref={problem} tabIndex={-1}><Alert type="error" showIcon title={revision ? '本批未确认保存' : '读取失败'} description={error} /></div>}
        <Flex gap={8} wrap><Button icon={<ReloadOutlined aria-hidden />} disabled={saving} onClick={() => confirmDiscard('重新读取选中页面？', () => setReload(value => value + 1))}>重新读取</Button><Button disabled={saving || !dirty} onClick={() => confirmDiscard('还原本次批量修改？', () => { setRows(base); setPrefix(''); setUniformType(undefined); })}>还原修改</Button></Flex>
        {revision && <>
          {!editable && <Alert type="warning" showIcon title="项目任务进行中，完成后重新读取即可编辑。" />}
          <Form layout="vertical" disabled={saving || !editable}>
            <div className="editor-outline-batch-tools"><Form.Item label="为选中标题添加前缀"><Space.Compact block><Input aria-label="标题前缀" maxLength={40} value={prefix} onChange={event => setPrefix(event.target.value)} /><Button disabled={!prefix || saving || !editable} onClick={addPrefix}>应用前缀</Button></Space.Compact></Form.Item><Form.Item label="统一页面类型"><Select aria-label="统一页面类型" placeholder="保留各页类型" value={uniformType} options={types} virtual={false} onChange={value => { setUniformType(value); setRows(current => current.map(row => ({ ...row, slideType: value }))); }} /></Form.Item></div>
            <Space orientation="vertical" size="middle" className="editor-outline-batch-form">{rows.map(row => <Card size="small" key={row.key} title={`第 ${row.index + 1} 页`}>
              <div className="editor-outline-batch-row"><Form.Item label="页面标题"><Input aria-label={`第 ${row.index + 1} 页标题`} maxLength={255} value={row.title} onChange={event => setRow(row.key, { title: event.target.value })} /></Form.Item><Form.Item label="页面类型"><Select aria-label={`第 ${row.index + 1} 页页面类型`} value={row.slideType} virtual={false} options={types.some(type => type.value === row.slideType) ? types : [...types, { value: row.slideType, label: row.slideType }]} onChange={value => setRow(row.key, { slideType: value })} /></Form.Item></div>
            </Card>)}</Space>
          </Form>
        </>}
      </>}
    </Space>
  </Drawer>;
}
