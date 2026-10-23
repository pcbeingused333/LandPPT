import { useEffect, useMemo, useRef, useState } from 'react';
import { App, Button, Empty, Flex, Input, Tag, Tooltip, Tree, type TreeDataNode } from 'antd';
import { AimOutlined, SearchOutlined } from '@ant-design/icons';
import { outlineParent, outlineTree, type OutlineNode, type OutlinePage } from './editor-outline-tree';
import { EditorOutlineOverview } from './editor-outline-overview';

export function EditorOutlineNavigation({ pages, current, visible, disabled, batchDisabled, onSelect, onBatchEdit }: {
  pages: OutlinePage[]; current: number; visible: boolean; disabled: boolean; batchDisabled: boolean; onSelect: (index: number) => void; onBatchEdit: (keys: string[]) => void;
}) {
  const { message } = App.useApp();
  const [batch, setBatch] = useState(false), [checked, setChecked] = useState<string[]>([]);
  const [query, setQuery] = useState(''), [collapsed, setCollapsed] = useState(new Set<string>());
  const [searchCollapsed, setSearchCollapsed] = useState(new Set<string>()), [locating, setLocating] = useState(0);
  const region = useRef<HTMLDivElement>(null);
  const tree = useMemo(() => outlineTree(pages), [pages]);
  const filtered = useMemo(() => outlineTree(pages, query), [pages, query]);
  const active = pages[current];
  const parent = active && outlineParent(tree, active.key);
  const searching = !!query.trim();
  const hidden = searching ? searchCollapsed : collapsed;
  const expanded = filtered.filter(node => node.children?.length && !hidden.has(node.key)).map(node => node.key);
  const chapterCount = tree.filter(node => node.chapter).length;
  const selected = checked.filter(key => pages.some(page => page.key === key));
  useEffect(() => {
    if (!active || !visible) return;
    if (parent) {
      const expand = (previous: Set<string>) => { if (!previous.has(parent)) return previous; const next = new Set(previous); next.delete(parent); return next; };
      setCollapsed(expand); setSearchCollapsed(expand);
    }
  }, [active?.key, parent, visible]);
  useEffect(() => {
    if (!visible) return;
    const frame = requestAnimationFrame(() => {
      const container = region.current, selected = container?.querySelector<HTMLElement>('.ant-tree-treenode-selected');
      if (!container || !selected) return;
      const bounds = container.getBoundingClientRect(), item = selected.getBoundingClientRect();
      if (item.top < bounds.top) container.scrollTop += item.top - bounds.top;
      else if (item.bottom > bounds.bottom) container.scrollTop += item.bottom - bounds.bottom;
    });
    return () => cancelAnimationFrame(frame);
  }, [active?.key, visible, query, locating, expanded.join('|')]);
  function locate() {
    setQuery(''); setSearchCollapsed(new Set()); setLocating(value => value + 1);
    const parent = active && outlineParent(tree, active.key);
    if (parent) setCollapsed(previous => { const next = new Set(previous); next.delete(parent); return next; });
  }
  function nodes(items: OutlineNode[]): TreeDataNode[] {
    return items.map(node => ({ key: node.key, selectable: true, disabled, children: node.children ? nodes(node.children) : undefined,
      title: <span className="editor-outline-title"><span className="editor-outline-number">{node.index + 1}</span><span>{node.title}</span>{node.chapter && <Tag>章节</Tag>}</span>,
    }));
  }
  return <section className="editor-outline-navigation" hidden={!visible} aria-label="文稿目录">
    <div className="editor-outline-search">
      <Input aria-label="搜索文稿目录" placeholder="搜索标题或页码" prefix={<SearchOutlined aria-hidden />} allowClear value={query} onChange={event => { setQuery(event.target.value); setSearchCollapsed(new Set()); }} />
      <Tooltip title="定位当前页"><Button aria-label="定位当前页" disabled={!active} icon={<AimOutlined aria-hidden />} onClick={locate} /></Tooltip>
    </div>
    <div className="editor-outline-summary" role="status">{pages.length} 页{chapterCount > 0 && ` · ${chapterCount} 个章节`}{active && <span title={active.title}>当前第 {current + 1} 页 · {active.title || '未命名'}</span>}</div>
    <Flex gap={8} className="editor-outline-batch-toggle"><EditorOutlineOverview pages={pages} current={current} visible={visible} disabled={disabled} onSelect={onSelect} /><Tooltip title={!batch && batchDisabled ? '请先保存或放弃未保存的大纲／讲稿修改' : undefined}><Button disabled={!pages.length || disabled || !batch && batchDisabled} onClick={() => { setBatch(value => !value); setChecked([]); }}>{batch ? '退出多选' : '批量编辑'}</Button></Tooltip></Flex>
    <div className="editor-outline-tree" ref={region}>
      {!filtered.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={pages.length ? '没有匹配的页面' : '暂无幻灯片'}>{pages.length > 0 && <Button onClick={() => { setQuery(''); setSearchCollapsed(new Set()); }}>清除搜索</Button>}</Empty> :
        <Tree aria-label="章节与页面" blockNode virtual={false} checkable={batch} checkStrictly checkedKeys={selected} treeData={nodes(filtered)} selectedKeys={active ? [active.key] : []} expandedKeys={expanded}
          onCheck={keys => { const values = (Array.isArray(keys) ? keys : keys.checked).map(String); if (values.length > 50) { void message.warning('一次最多编辑 50 页'); return; } setChecked(values); }}
          onExpand={keys => { const expandedSet = new Set(keys.map(String)); const next = new Set(filtered.filter(node => node.children?.length && !expandedSet.has(node.key)).map(node => node.key)); if (searching) setSearchCollapsed(next); else setCollapsed(next); }}
          onSelect={keys => { if (disabled || !keys.length) return; const index = pages.findIndex(page => page.key === keys[0]); if (index >= 0 && index !== current) onSelect(index); }} />}
    </div>
    {batch && <div className="editor-outline-batch-selection"><Flex justify="space-between" align="center" gap={8}><span>已选 {selected.length} 页</span><Button type="primary" disabled={!selected.length || disabled || batchDisabled} onClick={() => onBatchEdit(selected)}>编辑选中页</Button></Flex></div>}
  </section>;
}
