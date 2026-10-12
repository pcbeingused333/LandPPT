import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Skeleton } from 'antd';
import { CheckOutlined, FileImageOutlined, PauseOutlined, SyncOutlined } from '@ant-design/icons';
import type { ApiData } from '../api';

export type PreviewState = {
  visible: boolean; state: string; connectionClass: string;
  total?: number; completed?: number; activePages: number[];
};
type Preview = { number: number; failed: boolean };

export function GeneratorPreview({ data, state, unattendedStatus }: { data: ApiData; state: PreviewState; unattendedStatus?: string }) {
  const [host] = useState(() => {
    const element = document.createElement('div');
    element.id = 'generatorSkeletons';
    element.className = 'generator-skeleton-host';
    return element;
  });
  const [previews, setPreviews] = useState<Preview[]>([]);
  useEffect(() => {
    const grid = document.getElementById('slidesContainer');
    if (!grid) return;
    // The controller clears/rebuilds its preview grid on start and resume. Keep
    // this UI-only host separate from its slide IDs, data and iframe contents.
    function refresh() {
      if (!grid!.contains(host)) grid!.appendChild(host);
      const next = Array.from(grid!.children).filter(element => element.classList.contains('slide-card')).map(element => {
        const card = element as HTMLElement;
        const number = Number(card.dataset.slideIndex) + 1;
        card.style.order = String(number);
        return { number, failed: !!card.querySelector('[title="设计生成未完成，请重新生成此页"]') };
      });
      setPreviews(previous => JSON.stringify(previous) === JSON.stringify(next) ? previous : next);
    }
    const observer = new MutationObserver(refresh);
    observer.observe(grid, { childList: true });
    grid.dataset.previewMounted = 'true';
    refresh();
    return () => { observer.disconnect(); host.remove(); delete grid.dataset.previewMounted; };
  }, [host]);

  const target = document.getElementById('generatorPreviewUI');
  const titles: string[] = Array.isArray(data.slideTitles) ? data.slideTitles : [];
  const total = state.total || (state.state === 'complete' ? previews.length : titles.length);
  const ready = previews.filter(preview => !preview.failed).length;
  const completed = state.completed ?? ready;
  const terminalRun = ['completed', 'failed', 'cancelled'].includes(unattendedStatus || '');
  const phase = state.state === 'complete' ? 'complete'
    : state.state === 'error' || /error|failed|stopped/.test(state.connectionClass) || terminalRun ? 'stopped'
    : /paused/.test(state.connectionClass) ? 'paused'
    : /reconnecting|disconnected/.test(state.connectionClass) && state.visible ? 'reconnecting'
    : state.visible || data.unattendedActive ? 'running' : 'idle';
  const animate = phase === 'running';
  const pending: number[] = [];
  if (phase !== 'complete' && phase !== 'stopped') {
    const received = new Set(previews.map(preview => preview.number));
    if (total) {
      for (let number = 1; number <= total && pending.length < 6; number++) {
        if (!received.has(number)) pending.push(number);
      }
    } else {
      const last = Math.max(0, ...received);
      for (let index = 1; index <= 3; index++) pending.push(last + index);
    }
  }
  const heading = phase === 'complete' ? '演示文稿已生成' : phase === 'paused' ? '生成已暂停'
    : phase === 'reconnecting' ? '正在恢复连接' : phase === 'stopped' ? '生成暂未完成'
    : phase === 'idle' ? titles.length ? '大纲已就绪，准备生成' : '准备生成演示文稿' : ready ? '演示文稿正在成形' : '正在设计你的演示文稿';
  const hint = phase === 'complete' ? '打开编辑器继续调整，或开始幻灯片放映。'
    : phase === 'paused' ? '已生成的页面会保留，点击上方“继续”恢复生成。'
    : phase === 'reconnecting' ? '已生成的页面会保留，连接恢复后将继续更新。'
    : phase === 'stopped' ? '已生成的页面会保留，你可以重试未完成的页面。'
    : phase === 'idle' ? '点击上方“开始生成”，页面将按大纲依次呈现。'
    : '生成的页面会实时显示，可先预览已完成的页面。';

  return <>
    {target && createPortal(<section className={`generator-preview-summary is-${phase}`} aria-label="幻灯片预览概览">
      <div className="generator-preview-emblem" aria-hidden>{phase === 'complete' ? <CheckOutlined /> : phase === 'paused' ? <PauseOutlined /> : <FileImageOutlined />}</div>
      <div className="generator-preview-copy"><span className="generator-preview-eyebrow">实时预览 {animate && <SyncOutlined spin aria-hidden />}</span><h2>{heading}</h2><p>{hint}</p></div>
      <div className="generator-preview-count" aria-label={total ? `已生成 ${completed} / ${total} 页` : `已生成 ${completed} 页`}><strong>{completed}<span>{total ? ` / ${total}` : ' 页'}</span></strong><span>{phase === 'complete' ? '全部就绪' : total ? '页已生成' : '逐页更新'}</span></div>
    </section>, target)}
    {createPortal(pending.map(number => <article key={number} className={`generator-skeleton-card${state.activePages.includes(number) ? ' is-current' : ''}`} style={{ order: number }} aria-label={`第 ${number} 页：${titles[number - 1] || '待生成页面'}，${phase === 'paused' ? '已暂停' : '等待生成'}`}>
      <div className="generator-skeleton-header"><span className="generator-skeleton-number">{String(number).padStart(2, '0')}</span><span className="generator-skeleton-title" title={titles[number - 1] || '页面版式将在生成后显示'}>{titles[number - 1] || '待生成页面'}</span><span className="generator-skeleton-label">{phase === 'paused' ? '已暂停' : phase === 'reconnecting' ? '等待连接' : state.activePages.includes(number) ? '生成中' : '待生成'}</span></div>
      <div className="generator-skeleton-canvas" aria-hidden="true"><Skeleton active={animate} round title={{ width: '64%' }} paragraph={false} /><div className="generator-skeleton-content"><Skeleton active={animate} round title={false} paragraph={{ rows: 3, width: ['92%', '80%', '60%'] }} /><Skeleton.Node active={animate}><span /></Skeleton.Node></div><Skeleton active={animate} round title={{ width: '28%' }} paragraph={false} /></div>
    </article>), host)}
  </>;
}
