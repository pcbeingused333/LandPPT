import { useLayoutEffect } from 'react';
import { Alert, Button, Modal, Progress, Steps, Tag } from 'antd';
import { DownloadOutlined, FilePptOutlined, FileTextOutlined, LoadingOutlined, StopOutlined, SyncOutlined } from '@ant-design/icons';
import { modalFocus } from './modal-focus';

export type EditorExportProgress = {
  subtitle: string; status: string; percent: string;
  kind: 'working' | 'cancelling' | 'error' | 'success';
  cancelVisible: boolean; cancelDisabled: boolean; cancelLabel: string;
};
type Record = { node: HTMLElement; title: string; origin: HTMLElement | null; exportProgress?: EditorExportProgress };
type Props = { record: Record; index: number; projectTitle: string; cancel(): void; dismiss(): void };

// Follow the native progress messages, not a timer or guessed percentage.
function currentStage(progress: EditorExportProgress) {
  if (/生成\s*PPTX\s*文件|打包|下载|写入文件/.test(progress.status)) return 2;
  if (/正在处理第|^\s*\d+\s*\/\s*\d+\s*$/.test(progress.status) || /正在转换 SVG 页面/.test(progress.subtitle)) return 1;
  if (/准备|加载/.test(`${progress.status} ${progress.subtitle}`)) return 0;
  return -1;
}

function stageMessage(progress: EditorExportProgress) {
  const count = progress.status.match(/^\s*(\d+)\s*\/\s*(\d+)\s*$/);
  if (count) return `已转换 ${count[1]} / ${count[2]} 页`;
  if (/^准备中/.test(progress.status) || !progress.status) {
    return progress.subtitle.replace('准备渲染导出内容（低内存DOM模式）', '准备页面内容和字体').replace('加载图标导出规则', '准备页面中的图标资源') || '正在准备导出内容';
  }
  return progress.status;
}

export function EditorExportDialog({ record, index, projectTitle, cancel, dismiss }: Props) {
  const progress = record.exportProgress!;
  const error = progress.kind === 'error';
  const cancelling = progress.kind === 'cancelling';
  const raw = Number.parseFloat(progress.percent);
  const percent = Number.isFinite(raw) ? Math.round(Math.max(0, Math.min(100, raw))) : null;
  const stage = currentStage(progress);
  useLayoutEffect(() => {
    // The export can open before Ant transfers focus. Keep Escape from reaching
    // the workspace's selection shortcut during that interval as well.
    const key = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.preventDefault(); event.stopImmediatePropagation();
      if (error) dismiss();
    };
    document.addEventListener('keydown', key, true);
    return () => document.removeEventListener('keydown', key, true);
  }, [error, dismiss]);
  useLayoutEffect(() => {
    const node = record.node, role = node.getAttribute('role');
    node.classList.add('editor-ant-modal-host', 'editor-ant-export-host'); node.setAttribute('role', 'presentation');
    return () => {
      node.classList.remove('editor-ant-modal-host', 'editor-ant-export-host');
      if (role) node.setAttribute('role', role); else node.removeAttribute('role');
      queueMicrotask(() => {
        if (document.querySelector('.editor-ant-dialog')) return;
        const origin = record.origin?.isConnected && record.origin.getClientRects().length ? record.origin : document.querySelector<HTMLElement>('[data-editor-export-trigger]');
        origin?.focus({ preventScroll: true });
      });
    };
  }, [record.node, record.origin]);

  return <Modal open centered width={540} className="editor-ant-dialog editor-ant-export-dialog" zIndex={2000 + index * 20}
    title={record.title} aria-label={record.title} getContainer={() => record.node}
    closable={error ? { 'aria-label': '关闭导出窗口' } : false} keyboard={error} mask={{ closable: error }} onCancel={dismiss}
    modalRender={node => <div onKeyDownCapture={event => { if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); if (error) dismiss(); } }}>{modalFocus(node)}</div>}
    footer={<div className="editor-export-footer"><span>{error ? progress.status || '关闭后可重新发起导出。' : cancelling ? '正在终止当前转换任务，请稍候。' : '完成后将自动下载 PowerPoint 文件。'}</span>
      {error ? <Button type="primary" onClick={dismiss}>关闭</Button> : progress.cancelVisible && <Button aria-label={progress.cancelLabel || '取消导出'} icon={<StopOutlined aria-hidden />} disabled={progress.cancelDisabled} loading={cancelling} onClick={cancel}>{progress.cancelLabel || '取消导出'}</Button>}
    </div>}>
    <div className="editor-export-file"><span className="editor-export-emblem" aria-hidden><FilePptOutlined /></span><div><strong title={projectTitle}>{projectTitle || '演示文稿'}</strong><span>PowerPoint 演示文稿</span></div><Tag>PPTX</Tag></div>
    {error ? <Alert type="error" showIcon title="转换未完成" description={<div className="editor-export-error-detail">{progress.subtitle || '导出失败，请稍后重试。'}</div>} /> : <>
      <Steps className="editor-export-steps" size="small" responsive={false} current={stage} items={[
        { title: '准备内容', icon: <FileTextOutlined aria-hidden /> },
        { title: '转换页面', icon: <SyncOutlined aria-hidden /> },
        { title: '生成文件', icon: <DownloadOutlined aria-hidden /> },
      ]} />
      <section className="editor-export-progress" aria-label="PPTX 转换进度">
        <div className="editor-export-progress-heading"><span>{cancelling ? '正在取消导出' : progress.kind === 'success' ? '转换完成' : '转换进度'}</span><strong>{percent == null ? <><LoadingOutlined spin aria-hidden /> 处理中</> : `${percent}%`}</strong></div>
        {percent != null && <Progress percent={percent} strokeColor="var(--lp-primary)" showInfo={false} aria-label="PPTX 导出进度" />}
        <p role="status" aria-live="polite">{stageMessage(progress)}</p>
      </section>
    </>}
  </Modal>;
}
