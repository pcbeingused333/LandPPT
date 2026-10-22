import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Alert, App, Button, Empty, Input, Segmented, Select, Skeleton, Tag, Tooltip } from 'antd';
import { ArrowLeftOutlined, ArrowRightOutlined, DeleteOutlined, EditOutlined, EyeOutlined, FileTextOutlined, PlusOutlined, ReloadOutlined, RobotOutlined, SaveOutlined } from '@ant-design/icons';
import { request, type ApiData } from '../api';
import './editor-document-sidebar.css';

export type DocumentPage = { key: string; slideId: string | null; title: string };
export type DocumentBridge = {
  call(name: string, ...args: unknown[]): any;
  applyDocument(key: string, document: ApiData): void;
  openSpeechDocument(language: string, preview: boolean): void;
  saveDocument?: (() => Promise<void>) | null;
  setDocumentState?(state: { documentPanel: string; documentDirty: boolean; documentSaving: boolean }): void;
};
type Panel = 'slides' | 'outline' | 'speech';
type Draft = { value: ApiData; base: ApiData; revision: string; slideId: string | null; loading: boolean; saving: boolean; dirty: boolean; error: string; editing: boolean; source: ApiData };
const outlineValue = (outline: ApiData, title: string): ApiData => ({
  title: outline.title || title, slide_type: outline.slide_type || outline.type || 'content',
  subtitle: outline.subtitle || '', description: outline.description || '',
  ...(Array.isArray(outline.content_points) && outline.content_points.every((point: unknown) => typeof point === 'string') ? { content_points: outline.content_points } : !outline.content_points ? { content_points: [] } : {}),
  ...(outline.content === undefined || typeof outline.content === 'string' ? { content: outline.content || '' } : {}),
});
const speechValue = (script: ApiData | null, title: string): ApiData => ({
  slide_title: script?.slide_title || title, script_content: script?.script_content || '',
  estimated_duration: script?.estimated_duration || '', speaker_notes: script?.speaker_notes || '',
});

export function EditorDocumentSidebar({ projectId, pages, current, selected, dialogCount, bridge }: {
  projectId: string; pages: DocumentPage[]; current: number; selected: number; dialogCount: number; bridge: DocumentBridge;
}) {
  const { message, modal } = App.useApp();
  const [panel, setPanel] = useState<Panel>('slides'), [language, setLanguage] = useState('zh');
  const [, redraw] = useState(0), [reload, setReload] = useState(0);
  const drafts = useRef(new Map<string, Draft>()), pagesRef = useRef(pages), mounted = useRef(true);
  pagesRef.current = pages;
  const page = pages[current];
  const key = (kind: string, pageKey = page?.key, lang = language) => `${kind}:${pageKey}:${kind === 'speech' ? lang : ''}`;
  const draft = panel === 'slides' ? undefined : drafts.current.get(key(panel));
  const changed = () => { if (mounted.current) redraw(version => version + 1); };
  const dirtyCount = [...drafts.current.values()].filter(item => item.dirty).length;
  useLayoutEffect(() => {
    bridge.saveDocument = panel === 'slides' ? null : save;
    const sidebar = document.getElementById('slidesSidebar')!;
    sidebar.dataset.documentDirty = String(!!draft?.dirty && !draft.loading && !!draft.revision);
    sidebar.dataset.documentSaving = String(!!draft?.saving);
    bridge.setDocumentState?.({ documentPanel: panel, documentDirty: !!draft?.dirty && !draft.loading && !!draft.revision, documentSaving: !!draft?.saving });
    return () => { bridge.saveDocument = null; };
  });
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useLayoutEffect(() => {
    const sidebar = document.getElementById('slidesSidebar')!;
    sidebar.dataset.editorPanel = panel;
    return () => { delete sidebar.dataset.editorPanel; };
  }, [panel]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if ([...drafts.current.values()].some(item => item.dirty || item.saving)) { event.preventDefault(); event.returnValue = ''; }
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, []);
  useEffect(() => {
    if (panel === 'slides' || !page) return;
    const activeKey = key(panel), existing = drafts.current.get(activeKey);
    if (existing?.dirty || existing?.saving) return;
    const abort = new AbortController();
    const loading: Draft = existing || { value: {}, base: {}, revision: '', slideId: page.slideId, loading: true, saving: false, dirty: false, error: '', editing: panel === 'outline', source: {} };
    loading.loading = true; loading.error = ''; drafts.current.set(activeKey, loading); changed();
    const query = new URLSearchParams({ language }); if (page.slideId) query.set('slide_id', page.slideId);
    request(`/api/projects/${encodeURIComponent(projectId)}/editor-documents/${current}?${query}`, 'GET', undefined, abort.signal).then(result => {
      if (abort.signal.aborted) return;
      const document = result.document;
      if (!document || document.slide_index !== current || document.language !== language) throw new Error('页面数据不完整，请重试');
      for (const kind of ['outline', 'speech']) {
        const documentKey = key(kind, page.key, language), previous = drafts.current.get(documentKey);
        if (previous?.dirty || previous?.saving) continue;
        const value = kind === 'outline' ? outlineValue(document.outline, page.title) : speechValue(document.script, page.title);
        drafts.current.set(documentKey, { value, base: structuredClone(value), revision: document[`${kind}_revision`], slideId: document.slide_id, loading: false, saving: false, dirty: false, error: '', editing: previous?.editing ?? kind === 'outline', source: document });
      }
      // Refresh native metadata only when there is no local outline draft.
      if (!drafts.current.get(key('outline', page.key))?.dirty) bridge.applyDocument(page.key, document);
      changed();
    }).catch(error => {
      if (abort.signal.aborted) return;
      loading.error = error.message; loading.loading = false; changed();
    });
    return () => { abort.abort(); loading.loading = false; };
  }, [panel, page?.key, current, language, reload, dialogCount]);

  function edit(field: string, value: unknown) {
    if (!draft || draft.loading || draft.saving) return;
    draft.value = { ...draft.value, [field]: value };
    draft.dirty = JSON.stringify(draft.value) !== JSON.stringify(draft.base);
    changed();
  }
  function reset() {
    if (!draft || draft.saving) return;
    const active = draft;
    const discard = () => { active.value = structuredClone(active.base); active.dirty = false; active.error = ''; changed(); setReload(version => version + 1); };
    if (draft.dirty) modal.confirm({ title: '重新加载当前页？', content: '当前页的未保存修改会被丢弃，其他页和语言的草稿会保留。', okText: '重新加载', cancelText: '保留修改', onOk: discard });
    else discard();
  }
  async function save() {
    if (!draft || draft.loading || draft.saving || !draft.revision || !page || panel === 'slides') return;
    const active = draft, kind = panel, pageKey = page.key, lang = language;
    const index = pagesRef.current.findIndex(item => item.key === pageKey);
    if (index < 0) { active.error = '此页已删除，草稿仍保留'; changed(); return; }
    const value = structuredClone(active.value);
    if (!(kind === 'outline' ? value.title : value.script_content).trim()) { message.warning(kind === 'outline' ? '请填写页面标题' : '请填写讲稿正文'); return; }
    active.saving = true; active.error = ''; changed();
    try {
      const result = await request(`/api/projects/${encodeURIComponent(projectId)}/editor-documents/${index}?language=${lang}`, 'PATCH', {
        kind, revision: active.revision, slide_id: active.slideId, [kind]: value,
      });
      const document = result.document;
      const savedValue = kind === 'outline' ? outlineValue(document.outline, value.title) : speechValue(document.script, value.slide_title);
      active.value = savedValue; active.base = structuredClone(savedValue); active.source = document;
      active.revision = document[`${kind}_revision`]; active.dirty = false;
      bridge.applyDocument(pageKey, document);
      message.success(kind === 'outline' ? '大纲已保存' : '讲稿已保存');
    } catch (error) { active.error = (error as Error).message; }
    finally { active.saving = false; changed(); }
  }
  function switchPanel(value: string | number) { setPanel(value as Panel); }
  const sourceMissing = !draft?.source.script;
  const types = [{ value: 'title', label: '封面' }, { value: 'content', label: '内容页' }, { value: 'conclusion', label: '总结页' }];
  if (draft?.value.slide_type && !types.some(item => item.value === draft.value.slide_type)) types.push({ value: draft.value.slide_type, label: draft.value.slide_type });
  return <div className="editor-document-sidebar" onKeyDown={event => {
    // Keep native canvas shortcuts away from text fields and Ant popups.
    event.stopPropagation();
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's' && panel !== 'slides') { event.preventDefault(); void save(); }
  }}>
    <div className="editor-document-tabs"><Segmented block aria-label="左侧内容" value={panel} onChange={switchPanel} options={[
      { value: 'slides', label: '幻灯片' }, { value: 'outline', label: '大纲' }, { value: 'speech', label: '讲稿' },
    ]} /></div>
    {panel === 'slides' ? <div className="editor-document-selection">Ctrl+点击多选 · 已选 {selected} 页{dirtyCount > 0 && <Tag>{dirtyCount} 份草稿</Tag>}</div> : <>
      <div className="editor-document-nav">
        <Button aria-label="上一页" icon={<ArrowLeftOutlined aria-hidden />} disabled={current <= 0 || !!draft?.saving} onClick={() => bridge.call('selectSlide', current - 1)} />
        <Select aria-label="选择文稿页面" value={page ? current : undefined} disabled={!page || !!draft?.saving} showSearch optionFilterProp="label" options={pages.map((item, index) => ({ value: index, label: `${index + 1}. ${item.title || '未命名'}` }))} onChange={index => bridge.call('selectSlide', index)} />
        <Button aria-label="下一页" icon={<ArrowRightOutlined aria-hidden />} disabled={!page || current >= pages.length - 1 || !!draft?.saving} onClick={() => bridge.call('selectSlide', current + 1)} />
      </div>
      <div className="editor-document-tools">
        {panel === 'speech' ? <Select aria-label="讲稿语言" value={language} disabled={!!draft?.saving} options={[{ value: 'zh', label: '中文' }, { value: 'en', label: 'English' }]} onChange={setLanguage} /> : <span><FileTextOutlined aria-hidden /> 第 {current + 1} 页大纲</span>}
        <Tooltip title={draft?.editing ? '阅读模式' : '编辑模式'}><Button aria-label={draft?.editing ? '阅读文稿' : '编辑文稿'} disabled={!draft?.revision || draft.loading || draft.saving} icon={draft?.editing ? <EyeOutlined aria-hidden /> : <EditOutlined aria-hidden />} onClick={() => { if (draft) { draft.editing = !draft.editing; changed(); } }} /></Tooltip>
        <Tooltip title="重新加载当前页"><Button aria-label="重新加载文稿" disabled={!page || !!draft?.saving} icon={<ReloadOutlined aria-hidden />} onClick={reset} /></Tooltip>
      </div>
      <div className="editor-document-body" role="region" aria-label={panel === 'outline' ? '当前页大纲' : '当前页讲稿'} aria-busy={draft?.loading || draft?.saving}>
        {!page ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无幻灯片" /> : <>
          {draft?.error && <Alert type="error" showIcon title="暂时无法保存或加载" description={draft.error} />}
          {(!draft || draft.loading && !draft.revision) ? <Skeleton active paragraph={{ rows: 7 }} /> : !draft.revision ? <Button icon={<ReloadOutlined aria-hidden />} onClick={reset}>重试加载</Button> : <>
            {panel === 'outline' && <p className="editor-document-hint">用于生成和重新生成此页；保存后画面不会自动重绘。</p>}
            {!draft.editing ? <div className="editor-document-reading">
              {panel === 'outline' ? <><h2>{draft.value.title}</h2>{draft.value.subtitle && <p>{draft.value.subtitle}</p>}
                <Tag>{types.find(item => item.value === draft.value.slide_type)?.label}</Tag>
                {draft.value.content_points?.length > 0 && <ol>{draft.value.content_points.map((point: string, index: number) => <li key={index}>{point}</li>)}</ol>}
                {draft.value.description && <p>{draft.value.description}</p>}{draft.value.content && <p>{draft.value.content}</p>}
              </> : draft.value.script_content ? <><h2>{draft.value.slide_title}</h2>{draft.value.estimated_duration && <Tag>{draft.value.estimated_duration}</Tag>}<p>{draft.value.script_content}</p>{draft.value.speaker_notes && <aside><strong>演讲者备注</strong><p>{draft.value.speaker_notes}</p></aside>}</> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前页暂无讲稿"><Button type="primary" icon={<EditOutlined aria-hidden />} onClick={() => { draft.editing = true; changed(); }}>撰写讲稿</Button></Empty>}
            </div> : <fieldset disabled={draft.saving || draft.loading} className="editor-document-fields">
              <label>{panel === 'outline' ? '页面标题' : '讲稿标题'}<Input aria-label={panel === 'outline' ? '大纲标题' : '讲稿标题'} maxLength={255} value={draft.value[panel === 'outline' ? 'title' : 'slide_title']} onChange={event => edit(panel === 'outline' ? 'title' : 'slide_title', event.target.value)} /></label>
              {panel === 'outline' ? <>
                <label>页面类型<Select aria-label="大纲页面类型" value={draft.value.slide_type} options={types} disabled={draft.saving || draft.loading} onChange={value => edit('slide_type', value)} /></label>
                <label>副标题<Input aria-label="大纲副标题" value={draft.value.subtitle} onChange={event => edit('subtitle', event.target.value)} /></label>
                {draft.value.content_points ? <div className="editor-document-points"><strong>内容要点</strong>{draft.value.content_points.map((point: string, index: number) => <div className="editor-document-point" key={index}>
                  <span>{index + 1}</span><Input.TextArea aria-label={`大纲要点 ${index + 1}`} value={point} autoSize={{ minRows: 1, maxRows: 5 }} onChange={event => edit('content_points', draft.value.content_points.map((item: string, number: number) => number === index ? event.target.value : item))} />
                  <Button aria-label={`删除要点 ${index + 1}`} type="text" danger disabled={draft.saving} icon={<DeleteOutlined aria-hidden />} onClick={() => edit('content_points', draft.value.content_points.filter((_: string, number: number) => number !== index))} />
                </div>)}<Button icon={<PlusOutlined aria-hidden />} disabled={draft.saving || draft.value.content_points.length >= 100} onClick={() => edit('content_points', [...draft.value.content_points, ''])}>添加要点</Button></div> : <p className="editor-document-hint">此页使用结构化要点，保留其原始内容。</p>}
                <label>页面说明<Input.TextArea aria-label="大纲说明" autoSize={{ minRows: 3, maxRows: 8 }} value={draft.value.description} onChange={event => edit('description', event.target.value)} /></label>
                {'content' in draft.value && <label>补充正文<Input.TextArea aria-label="大纲正文" autoSize={{ minRows: 2, maxRows: 6 }} value={draft.value.content} onChange={event => edit('content', event.target.value)} /></label>}
              </> : <>
                {sourceMissing && <p className="editor-document-hint">可直接撰写并保存，也可使用 AI 生成讲稿。</p>}
                <label>讲稿正文<Input.TextArea aria-label="讲稿正文" value={draft.value.script_content} autoSize={{ minRows: 9, maxRows: 24 }} onChange={event => edit('script_content', event.target.value)} /></label>
                <label>预计时长<Input aria-label="讲稿预计时长" placeholder="例如：2分钟" maxLength={50} value={draft.value.estimated_duration} onChange={event => edit('estimated_duration', event.target.value)} /></label>
                <label>演讲者备注<Input.TextArea aria-label="演讲者备注" autoSize={{ minRows: 3, maxRows: 8 }} value={draft.value.speaker_notes} onChange={event => edit('speaker_notes', event.target.value)} /></label>
              </>}
            </fieldset>}
            {panel === 'speech' && <div className="editor-document-speech-actions"><Button icon={<RobotOutlined aria-hidden />} disabled={draft.saving} onClick={() => bridge.openSpeechDocument(language, false)}>生成讲稿</Button><Button icon={<EyeOutlined aria-hidden />} disabled={draft.saving} onClick={() => bridge.openSpeechDocument(language, true)}>查看全部</Button></div>}
          </>}
        </>}
      </div>
      <footer className="editor-document-footer"><div role="status">{draft?.saving ? '正在保存…' : draft?.dirty ? '当前页有未保存修改' : draft?.revision ? '与服务器同步' : '等待加载'}{dirtyCount > 1 && <small>共 {dirtyCount} 份草稿</small>}</div>
        <Button type="primary" icon={<SaveOutlined aria-hidden />} loading={draft?.saving} disabled={!draft?.dirty || draft.loading || !draft.revision} onClick={() => void save()}>保存{panel === 'outline' ? '大纲' : '讲稿'}</Button></footer>
    </>}
  </div>;
}
