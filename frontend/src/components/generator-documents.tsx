import { useEffect, useRef, useState } from 'react';
import { Button, Card, Flex, Modal, Space, Tag, Typography } from 'antd';
import { ExpandOutlined, LeftOutlined, RightOutlined } from '@ant-design/icons';
import type { GeneratorSlide } from '../controllers/generator-controller';
import { SlideDocument } from './slide-document';
import { modalFocus } from './modal-focus';
import './generator-documents.css';

export function GeneratorDocuments({ slides }: { slides: GeneratorSlide[] }) {
  const [selected, setSelected] = useState<number>();
  const origin = useRef<HTMLElement | null>(null);
  const index = slides.findIndex(slide => slide.page_number === selected);
  const current = slides[index];
  const close = () => setSelected(undefined);
  const navigate = (offset: number) => {
    const next = slides[index + offset];
    if (next) setSelected(next.page_number);
  };
  const keys = (event: KeyboardEvent) => {
    if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey) return;
    if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(); }
    else if (!event.isComposing && !(event.target as HTMLElement | null)?.closest?.('input,textarea,select,[contenteditable]:not([contenteditable="false"]),[role="textbox"],audio,video') && ['ArrowLeft', 'ArrowRight'].includes(event.key)) {
      event.preventDefault(); navigate(event.key === 'ArrowLeft' ? -1 : 1);
    }
  };
  useEffect(() => {
    if (selected !== undefined && !current) close();
  }, [selected, current]);
  useEffect(() => {
    if (!current) return;
    document.addEventListener('keydown', keys);
    window.addEventListener('pagehide', close);
    return () => { document.removeEventListener('keydown', keys); window.removeEventListener('pagehide', close); };
  });
  return <>
    {slides.map(slide => <Card key={slide.page_number} id={`slide-${slide.page_number}`} className="slide-card" size="small" style={{ order: slide.page_number }}
      classNames={{ header: 'slide-header' }} styles={{ body: { padding: 0 } }}
      title={<Typography.Text className="slide-title" title={slide.title || `第 ${slide.page_number} 页`} ellipsis>{slide.title || `第 ${slide.page_number} 页`}</Typography.Text>}
      extra={<Space size={4}>
        <Tag>第 {slide.page_number} 页</Tag>
        {slide.generation_failed && !slide.is_user_edited && <Tag color="error" role="status" title="设计生成未完成，请重新生成此页">未完成</Tag>}
        {slide.render_mode === 'svg' && <Tag title="SVG 实验页">SVG</Tag>}
        <Button className="fullscreen-btn" title="全屏查看" aria-label={`全屏查看第 ${slide.page_number} 页`} icon={<ExpandOutlined aria-hidden />} onClick={event => { origin.current = event.currentTarget; setSelected(slide.page_number); }} />
      </Space>}>
      <div className="slide-preview"><SlideDocument html={slide.html_content} title={`Slide ${slide.page_number}`} /></div>
    </Card>)}
    <Modal centered destroyOnHidden open={!!current} title={current ? `第 ${current.page_number} 页 · ${current.title || '未命名页面'}` : '页面预览'} width="calc(100vw - 32px)" className="generator-document-modal"
      onCancel={close} afterClose={() => { if (origin.current?.isConnected) origin.current.focus(); }} modalRender={modalFocus}
      footer={<Flex justify="space-between" align="center" gap={8} wrap><Typography.Text type="secondary">← → 翻页 · Esc 关闭</Typography.Text><Space><Button icon={<LeftOutlined aria-hidden />} disabled={index <= 0} onClick={() => navigate(-1)}>上一页</Button><Typography.Text aria-live="polite">{index + 1} / {slides.length}</Typography.Text><Button disabled={index < 0 || index === slides.length - 1} onClick={() => navigate(1)}>下一页 <RightOutlined aria-hidden /></Button></Space></Flex>}>
      {current && <SlideDocument html={current.html_content} title="幻灯片全屏预览" interactive contain onKeyDown={keys} />}
    </Modal>
  </>;
}
