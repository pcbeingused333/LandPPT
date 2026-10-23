export type OutlinePage = { key: string; title: string; slideType?: string };
export type OutlineNode = { key: string; title: string; index: number; chapter: boolean; children?: OutlineNode[] };
export type OutlineGroup = { key: string; title: string; chapter: boolean; pages: OutlineNode[] };
const chapterTypes = new Set(['transition', 'section', 'section_transition', 'section_divider', 'chapter_divider']);

// Only explicit divider types establish chapters. Titles never invent structure.
export function outlineTree(pages: OutlinePage[], query = ''): OutlineNode[] {
  const roots: OutlineNode[] = [];
  let chapter: OutlineNode | undefined;
  pages.forEach((page, index) => {
    const node: OutlineNode = { key: page.key, title: page.title || '未命名', index, chapter: chapterTypes.has(page.slideType || '') };
    if (node.chapter) { roots.push(node); chapter = node; }
    else if (chapter) (chapter.children ||= []).push(node);
    else roots.push(node);
  });
  const text = query.trim().toLocaleLowerCase();
  if (!text) return roots;
  const matches = (node: OutlineNode) => node.title.toLocaleLowerCase().includes(text) || String(node.index + 1) === text;
  return roots.flatMap(node => {
    if (matches(node)) return [node];
    const children = node.children?.filter(matches);
    return children?.length ? [{ ...node, children }] : [];
  });
}

export function outlineParent(nodes: OutlineNode[], key: string): string | undefined {
  return nodes.find(node => node.children?.some(child => child.key === key))?.key;
}

// Overview cards share the directory's explicit chapter rules and absolute
// indices. Leading pages are a display group, never an invented chapter.
export function outlineGroups(pages: OutlinePage[], query = ''): OutlineGroup[] {
  const tree = outlineTree(pages, query), loose = tree.filter(node => !node.chapter);
  const groups = tree.filter(node => node.chapter).map(node => ({ key: 'chapter:' + node.key, title: node.title, chapter: true, pages: [node, ...node.children || []] }));
  if (loose.length) groups.unshift({ key: 'unsectioned', title: outlineTree(pages).some(node => node.chapter) ? '未分章节' : '全部页面', chapter: false, pages: loose });
  return groups;
}
