import { useLayoutEffect } from 'react';
import { Button, Input, Modal, Space, Tag, Tooltip } from 'antd';
import { CheckCircleOutlined, CopyOutlined, ExportOutlined, LinkOutlined, AudioOutlined, StopOutlined } from '@ant-design/icons';
import { modalFocus } from './modal-focus';

export type EditorShareLinks = { presentation: string; narration: string };
export type EditorShareAction = 'copy' | 'open' | 'copyNarration' | 'openNarration' | 'disable';
type Record = { node: HTMLElement; origin: HTMLElement | null; shareLinks?: EditorShareLinks };
type Props = { record: Record; index: number; projectTitle: string; run(action: EditorShareAction): void; dismiss(): void };

// Render link controls while the original buttons retain their request handlers.
export function EditorShareDialog({ record, index, projectTitle, run, dismiss }: Props) {
  const links = record.shareLinks!;
  useLayoutEffect(() => {
    const node = record.node, role = node.getAttribute('role'), modal = node.getAttribute('aria-modal');
    node.classList.add('editor-ant-modal-host', 'editor-ant-share-host');
    node.setAttribute('role', 'presentation'); node.removeAttribute('aria-modal');
    return () => {
      node.classList.remove('editor-ant-modal-host', 'editor-ant-share-host');
      if (role) node.setAttribute('role', role); else node.removeAttribute('role');
      if (modal) node.setAttribute('aria-modal', modal);
      queueMicrotask(() => {
        if (document.querySelector('.editor-ant-dialog')) return;
        const origin = record.origin?.isConnected && record.origin.getClientRects().length ? record.origin : document.querySelector<HTMLElement>('[aria-label="更多工具"]');
        origin?.focus({ preventScroll: true });
      });
    };
  }, [record.node, record.origin]);

  function linkCard(narration = false) {
    const url = narration ? links.narration : links.presentation;
    const label = narration ? '讲解链接' : '演示链接';
    const copyLabel = narration ? '复制讲解链接' : '复制链接';
    const openLabel = narration ? '打开讲解' : '打开演示';
    return <section className="editor-share-link-card" aria-label={label}>
      <div className="editor-share-link-heading"><span aria-hidden>{narration ? <AudioOutlined /> : <LinkOutlined />}</span><strong>{label}</strong><span>{narration ? '附带演讲稿讲解' : '浏览与播放幻灯片'}</span></div>
      <Space.Compact block>
        <Input aria-label={label} title={url} value={url} readOnly onFocus={event => event.target.select()} />
        <Tooltip title={copyLabel} trigger={['hover', 'focus']}><Button aria-label={copyLabel} type="primary" icon={<CopyOutlined aria-hidden />} onClick={() => run(narration ? 'copyNarration' : 'copy')} /></Tooltip>
        <Tooltip title={openLabel} trigger={['hover', 'focus']}><Button aria-label={openLabel} icon={<ExportOutlined aria-hidden />} onClick={() => run(narration ? 'openNarration' : 'open')} /></Tooltip>
      </Space.Compact>
    </section>;
  }

  return <Modal open centered width={560} title="分享链接" aria-label="分享链接" className="editor-ant-dialog editor-ant-share-dialog" zIndex={2000 + index * 20}
    getContainer={() => record.node} closable={{ 'aria-label': '关闭分享弹窗' }} onCancel={dismiss}
    modalRender={node => <div onKeyDownCapture={event => { if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); dismiss(); } }}>{modalFocus(node)}</div>}
    footer={<div className="editor-share-footer"><Button type="text" danger icon={<StopOutlined aria-hidden />} onClick={() => run('disable')}>禁用分享</Button><Button onClick={dismiss}>关闭</Button></div>}>
    <div className="editor-share-overview"><span className="editor-share-emblem" aria-hidden><LinkOutlined /></span><div><strong title={projectTitle}>{projectTitle || '演示文稿'}</strong><span>复制或打开下方链接。</span></div><Tag icon={<CheckCircleOutlined aria-hidden />}>已启用</Tag></div>
    <div className="editor-share-links">{linkCard()}{links.narration && linkCard(true)}</div>
    <p className="editor-share-hint">禁用后，已有分享链接将无法访问。</p>
  </Modal>;
}
