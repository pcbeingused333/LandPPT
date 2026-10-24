import { Button, Empty } from 'antd';
import { EditOutlined } from '@ant-design/icons';
import { SlideDocument } from './slide-document';

export function ContinuousPreview({ pages, onEdit }: { pages: { title: string; html: string }[]; onEdit: (index: number) => void }) {
  return <section className="continuous-preview" aria-label="连续幻灯片预览">
    {!pages.length && <Empty description="生成页面后，演示文稿会显示在这里" />}
    {pages.map((page, index) => <article key={index} className="continuous-slide" data-slide-index={index}>
      <header><span><b>{String(index + 1).padStart(2, '0')}</b>{page.title || '未命名页面'}</span><Button size="small" type="text" icon={<EditOutlined aria-hidden />} aria-label={`编辑第 ${index + 1} 页`} onClick={() => onEdit(index)}>编辑</Button></header>
      <SlideDocument html={page.html || ''} title={`连续预览第 ${index + 1} 页`} />
    </article>)}
  </section>;
}
