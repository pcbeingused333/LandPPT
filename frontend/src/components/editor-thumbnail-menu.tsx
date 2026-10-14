import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { Dropdown } from 'antd';
import type { MenuProps } from 'antd';
import { CodeOutlined, CopyOutlined, DeleteOutlined, DownloadOutlined, FileAddOutlined, FileTextOutlined, ReloadOutlined, SnippetsOutlined } from '@ant-design/icons';

export type EditorContextMenu = {
  x: number; y: number; index: number; title: string;
  actions: Record<string, { disabled: boolean; hidden: boolean; hint: string }>;
};

type Props = {
  state: EditorContextMenu | null;
  run(action: string): void;
  dismiss(): void;
};

// Menu presentation only: the native controller remains the source of actions
// and availability, including its clipboard and generation guards.
export function EditorThumbnailMenu({ state, run, dismiss }: Props) {
  const [size, setSize] = useState(() => ({ width: 252, height: window.innerWidth <= 700 ? 498 : 390 }));
  const observer = useRef<ResizeObserver | null>(null);
  const measure = useCallback((node: HTMLDivElement | null) => {
    observer.current?.disconnect(); observer.current = null;
    if (!node) return;
    const update = () => {
      const { width, height } = node.getBoundingClientRect();
      if (width && height) setSize(previous => Math.abs(previous.width - width) < .5 && Math.abs(previous.height - height) < .5 ? previous : { width, height });
    };
    observer.current = new ResizeObserver(update); observer.current.observe(node); update();
  }, []);
  const x = Math.max(8, Math.min(state?.x || 8, window.innerWidth - Math.min(size.width, window.innerWidth - 16) - 8));
  const y = Math.max(8, Math.min(state?.y || 8, window.innerHeight - Math.min(size.height, window.innerHeight - 16) - 8));
  useLayoutEffect(() => {
    const native = document.getElementById('contextMenu');
    if (!native) return;
    native.dataset.antMenuMounted = 'true';
    return () => { delete native.dataset.antMenuMounted; };
  }, []);

  useEffect(() => {
    if (!state) return;
    const thumbnail = document.querySelector<HTMLElement>(`.slide-thumbnail[data-slide-index="${state.index}"]`);
    const keys = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' && event.key !== 'Tab') return;
      event.preventDefault(); event.stopImmediatePropagation();
      dismiss(); thumbnail?.focus({ preventScroll: true });
    };
    const close = () => dismiss();
    const context = (event: MouseEvent) => {
      if (!(event.target instanceof Element) || !event.target.closest('.slide-thumbnail, .editor-thumbnail-menu')) dismiss();
    };
    const pane = document.querySelector('.slides-container');
    // Focusing an offscreen thumbnail scrolls before contextmenu, but its
    // queued scroll event can arrive after the menu opens. Close only when
    // the list actually moves from the position where this menu opened.
    const originTop = pane?.scrollTop, originLeft = pane?.scrollLeft;
    const scroll = () => { if (pane?.scrollTop !== originTop || pane?.scrollLeft !== originLeft) dismiss(); };
    document.addEventListener('keydown', keys, true);
    document.addEventListener('contextmenu', context);
    window.addEventListener('resize', close);
    pane?.addEventListener('scroll', scroll);
    return () => {
      document.removeEventListener('keydown', keys, true);
      document.removeEventListener('contextmenu', context);
      window.removeEventListener('resize', close);
      pane?.removeEventListener('scroll', scroll);
    };
  }, [state?.index, dismiss, !!state]);

  const item = (key: string, label: string, icon: ReactNode, danger = false) => {
    const action = state?.actions[key];
    return !action || action.hidden ? [] : [{ key, label, icon, danger, disabled: action.disabled, title: action.disabled ? action.hint : undefined }];
  };
  const items: MenuProps['items'] = state ? [
    ...item('editSlide', '编辑代码', <CodeOutlined aria-hidden />),
    ...item('regenerateContextSlide', '重新生成', <ReloadOutlined aria-hidden />),
    { type: 'divider' },
    ...item('copySlide', '复制到剪贴板', <CopyOutlined aria-hidden />),
    ...item('pasteSlide', '粘贴到此页之后', <SnippetsOutlined aria-hidden />),
    ...item('duplicateSlide', '创建副本', <CopyOutlined aria-hidden />),
    ...item('insertNewSlide', '插入新幻灯片', <FileAddOutlined aria-hidden />),
    { type: 'divider' },
    ...item('exportSingleSlideHTML', '导出 HTML', <FileTextOutlined aria-hidden />),
    ...item('exportSingleSlidePptxClient', '导出单页 PPTX', <DownloadOutlined aria-hidden />),
    { type: 'divider' },
    ...item('deleteSlide', '删除幻灯片', <DeleteOutlined aria-hidden />, true),
  ] : [];

  return <Dropdown key={state ? `${state.index}:${x}:${y}` : 'closed'} open={!!state} trigger={[]} autoFocus autoAdjustOverflow={false} align={{ offset: [0, 0] }} destroyOnHidden placement="bottomLeft"
    classNames={{ root: 'editor-thumbnail-dropdown' }}
    styles={{ root: { padding: 0, zIndex: 1600, position: 'fixed' } }}
    onOpenChange={open => { if (!open) dismiss(); }}
    menu={{ items, 'aria-label': '幻灯片操作', onClick: ({ key }) => {
      document.querySelector<HTMLElement>(`.slide-thumbnail[data-slide-index="${state?.index}"]`)?.focus({ preventScroll: true });
      run(key);
    } }}
    popupRender={menu => <div className="editor-thumbnail-menu" ref={measure}
      onFocus={event => { if (event.target === event.currentTarget) event.currentTarget.querySelector<HTMLElement>('[role="menuitem"]:not([aria-disabled="true"])')?.focus({ preventScroll: true }); }} onContextMenu={event => event.preventDefault()} tabIndex={-1}>
      <header><span className="editor-thumbnail-menu-number">{(state?.index ?? 0) + 1}</span><div><span>幻灯片操作</span><strong title={state?.title}>{state?.title || '未命名幻灯片'}</strong></div></header>
      {menu}
    </div>}>
    <span className="editor-thumbnail-anchor" aria-hidden style={{ left: x, top: y }} />
  </Dropdown>;
}
