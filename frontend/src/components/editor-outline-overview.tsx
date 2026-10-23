import { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Card, Drawer, Empty, Flex, Input, Space, Tag, Tooltip, Typography } from 'antd';
import { AimOutlined, ApartmentOutlined, SearchOutlined } from '@ant-design/icons';
import { outlineGroups, type OutlinePage } from './editor-outline-tree';
import { modalFocus } from './modal-focus';

export function EditorOutlineOverview({ pages, current, visible, disabled, onSelect }: {
  pages: OutlinePage[]; current: number; visible: boolean; disabled: boolean; onSelect: (index: number) => void;
}) {
  const [open, setOpen] = useState(false), [query, setQuery] = useState(''), [locating, setLocating] = useState(0);
  const trigger = useRef<HTMLButtonElement>(null), closeButton = useRef<HTMLButtonElement>(null), region = useRef<HTMLElement>(null);
  const groups = useMemo(() => outlineGroups(pages, query), [pages, query]);
  const chapters = useMemo(() => outlineGroups(pages).filter(group => group.chapter).length, [pages]);
  const active = pages[current];
  useEffect(() => { if (!visible) setOpen(false); }, [visible]);
  useEffect(() => {
    if (!open) return;
    // Tooltips can consume Escape before React bubbling. This temporary modal
    // boundary also covers the opening transition; remove it on close/unmount.
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === 'Escape' || (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
        event.preventDefault(); event.stopPropagation();
        if (event.key === 'Escape') setOpen(false);
      }
    };
    window.addEventListener('keydown', keyboard, true);
    return () => window.removeEventListener('keydown', keyboard, true);
  }, [open]);
  // Only an explicit locate request moves focus; typing a matching title later
  // must not pull focus away from the search field.
  useEffect(() => {
    if (!open || !locating) return;
    const frame = requestAnimationFrame(() => {
      const button = region.current?.querySelector<HTMLButtonElement>('[aria-current="page"]');
      button?.scrollIntoView({ block: 'nearest', inline: 'nearest' }); button?.focus({ preventScroll: true });
    });
    return () => cancelAnimationFrame(frame);
  }, [locating, open]);
  return <>
    <Button icon={<ApartmentOutlined aria-hidden />} disabled={!pages.length || disabled} onClick={() => { setQuery(''); setLocating(0); setOpen(true); }} ref={trigger}>结构总览</Button>
    <Drawer title="文稿结构总览" open={open} onClose={() => setOpen(false)} size={1024} zIndex={1700} className="editor-outline-overview" styles={{ wrapper: { maxWidth: '100vw' } }} autoFocus={false} destroyOnHidden
      afterOpenChange={value => {
        if (value) { const section = closeButton.current?.closest('[role="dialog"]'); if (!section?.contains(document.activeElement) || section === document.activeElement) closeButton.current?.focus({ preventScroll: true }); }
        else if (visible && trigger.current?.isConnected) trigger.current.focus({ preventScroll: true });
      }}
      drawerRender={node => <div style={{ height: '100%' }} onKeyDown={event => { event.stopPropagation(); if (event.key === 'Escape') { event.preventDefault(); setOpen(false); } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') event.preventDefault(); }}>{modalFocus(node, { height: '100%' })}</div>}
      footer={<Flex align="center" justify="space-between" gap={12}><Typography.Text type="secondary">{active ? `当前第 ${current + 1} 页 · 共 ${pages.length} 页` : `共 ${pages.length} 页`}</Typography.Text><Button ref={closeButton} autoFocus onClick={() => setOpen(false)}>关闭</Button></Flex>}>
      <Space orientation="vertical" size="middle" className="editor-overview-body">
        <Flex align="center" justify="space-between" gap={8} wrap><Typography.Text>{pages.length} 页 · {chapters} 个章节{query.trim() ? ' · 已筛选' : ''}</Typography.Text><Typography.Text type="secondary">仅按已有章节过渡页分组，点击页面回到编辑器。</Typography.Text></Flex>
        <Flex gap={8} className="editor-overview-toolbar"><Input aria-label="搜索结构总览" placeholder="搜索标题或页码" allowClear prefix={<SearchOutlined aria-hidden />} value={query} onChange={event => setQuery(event.target.value)} /><Tooltip title="清除筛选并定位当前页"><Button aria-label="在结构总览定位当前页" disabled={!active} icon={<AimOutlined aria-hidden />} onClick={() => { setQuery(''); setLocating(value => value + 1); }}>当前页</Button></Tooltip></Flex>
        <section aria-label="章节结构卡片" className="editor-overview-groups" ref={region}>
          {groups.map(group => <Card key={group.key} size="small" title={<Typography.Text ellipsis={{ tooltip: group.title }}>{group.title}</Typography.Text>} extra={<Tag>{group.pages.length} 页</Tag>}>
            <Flex vertical gap={8}>
              {group.pages.map(page => <Tooltip title={page.title} key={page.key}><Button className="editor-overview-page" type={page.key === active?.key ? 'primary' : 'default'} aria-current={page.key === active?.key ? 'page' : undefined} aria-label={`转到第 ${page.index + 1} 页：${page.title}`} disabled={disabled} onClick={() => { const index = pages.findIndex(item => item.key === page.key); if (index >= 0 && !disabled) { if (index !== current) onSelect(index); setOpen(false); } }}>
                <span className="editor-overview-page-number">{page.index + 1}</span><span className="editor-overview-page-title">{page.title}</span>{page.chapter && <Tag>章节页</Tag>}{page.key === active?.key && <span>当前</span>}
              </Button></Tooltip>)}
            </Flex>
          </Card>)}
        </section>
        {!groups.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={pages.length ? '没有匹配的页面' : '暂无幻灯片'}>{pages.length > 0 && <Button onClick={() => setQuery('')}>清除搜索</Button>}</Empty>}
      </Space>
    </Drawer>
  </>;
}
