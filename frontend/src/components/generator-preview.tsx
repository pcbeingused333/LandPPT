import { Card, Skeleton, Tag, Typography } from 'antd';
import type { ApiData } from '../api';
import type { GeneratorSlide } from '../controllers/generator-controller';
import { GeneratorDocuments } from './generator-documents';

export type PreviewState = {
  visible: boolean; state: string; connectionClass: string;
  total?: number; completed?: number; activePages: number[]; slides: GeneratorSlide[];
};

export function GeneratorPreview({ data, state, unattendedStatus }: { data: ApiData; state: PreviewState; unattendedStatus?: string }) {
  const previews = state.slides.map(slide => ({ number: slide.page_number, failed: !!slide.generation_failed && !slide.is_user_edited }));
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
  const heading = phase === 'paused' ? '生成已暂停'
    : phase === 'reconnecting' ? '正在恢复连接' : phase === 'stopped' ? '生成暂未完成'
    : phase === 'idle' ? titles.length ? '大纲已就绪，准备生成' : '准备生成演示文稿' : '页面预览';
  const hint = phase === 'paused' ? '已生成的页面会保留，点击上方“继续”恢复生成。'
    : phase === 'reconnecting' ? '已生成的页面会保留，连接恢复后将继续更新。'
    : phase === 'stopped' ? '已生成的页面会保留，你可以重试未完成的页面。'
    : phase === 'idle' ? '点击上方“开始生成”，页面将按大纲依次呈现。'
    : '';

  return <>
    <div id="generatorPreviewUI"><section className={`generator-preview-summary is-${phase}`} aria-label="幻灯片预览概览">
      <div className="generator-preview-copy"><h2>{heading}</h2>{hint && <p>{hint}</p>}</div>
      <div className="generator-preview-count" aria-label={total ? `已生成 ${completed} / ${total} 页` : `已生成 ${completed} 页`}><strong>{completed}<span>{total ? ` / ${total}` : ' 页'}</span></strong></div>
    </section></div>
    <div id="slidesContainer" className="slides-container">
    <GeneratorDocuments slides={state.slides} />
    <div id="generatorSkeletons" className="generator-skeleton-host">{pending.map(number => <Card key={number} size="small" className={`generator-skeleton-card${state.activePages.includes(number) ? ' is-current' : ''}`} style={{ order: number }} role="group" aria-label={`第 ${number} 页：${titles[number - 1] || '待生成页面'}，${phase === 'paused' ? '已暂停' : '等待生成'}`}
      classNames={{ header: 'generator-skeleton-header' }} styles={{ body: { padding: 0 } }}
      title={<div className="generator-skeleton-title-row"><span className="generator-skeleton-number">{String(number).padStart(2, '0')}</span><Typography.Text className="generator-skeleton-title" type="secondary" ellipsis title={titles[number - 1] || '页面版式将在生成后显示'}>{titles[number - 1] || '待生成页面'}</Typography.Text></div>}
      extra={<Tag className="generator-skeleton-label">{phase === 'paused' ? '已暂停' : phase === 'reconnecting' ? '等待连接' : state.activePages.includes(number) ? '生成中' : '待生成'}</Tag>}>
      <div className="generator-skeleton-canvas" aria-hidden="true"><Skeleton active={animate} round title={{ width: '64%' }} paragraph={false} /><div className="generator-skeleton-content"><Skeleton active={animate} round title={false} paragraph={{ rows: 3, width: ['92%', '80%', '60%'] }} /><Skeleton.Node active={animate}><span /></Skeleton.Node></div><Skeleton active={animate} round title={{ width: '28%' }} paragraph={false} /></div>
    </Card>)}</div>
    </div>
  </>;
}
