import { useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { AlignCenterOutlined, AlignLeftOutlined, AlignRightOutlined, ArrowDownOutlined, BoldOutlined, CloseOutlined, CopyOutlined, DeleteOutlined, DiffOutlined, ExpandOutlined, EyeOutlined, HistoryOutlined, ItalicOutlined, MinusOutlined, PlusOutlined, RedoOutlined, RobotOutlined, SaveOutlined, StopOutlined, UnderlineOutlined, UndoOutlined, UpOutlined } from '@ant-design/icons';

const toolbarIcons = [
  ['quickEditUndo', UndoOutlined], ['quickEditRedo', RedoOutlined], ['quickEditDelete', DeleteOutlined],
  ['quickEditDuplicate', CopyOutlined], ['quickEditDecreaseFontSize', MinusOutlined], ['quickEditIncreaseFontSize', PlusOutlined],
  ['quickEditToggleBold', BoldOutlined], ['quickEditToggleItalic', ItalicOutlined], ['quickEditToggleUnderline', UnderlineOutlined],
  ['quickEditMoveUp', UpOutlined], ['quickEditMoveDown', ArrowDownOutlined], ['quickEditAlignLeft', AlignLeftOutlined],
  ['quickEditAlignCenter', AlignCenterOutlined], ['quickEditAlignRight', AlignRightOutlined], ['quickEditReset', HistoryOutlined],
  ['toggleQuickAiEditPopover', RobotOutlined],
] as const;
const resultIcons = { 'fa-save': SaveOutlined, 'fa-check': SaveOutlined, 'fa-stop': StopOutlined, 'fa-undo': UndoOutlined, 'fa-rotate-left': UndoOutlined, 'fa-rotate-right': RedoOutlined, 'fa-code': DiffOutlined, 'fa-code-compare': DiffOutlined, 'fa-spinner': HistoryOutlined };
type Icon = typeof RobotOutlined;
type Target = { node: HTMLElement; Icon: Icon; key: string };

// Keep native buttons/listeners; their icon artwork comes from local Ant assets.
export function EditorQuickIcons() {
  const [targets, setTargets] = useState<Target[]>([]);
  const previous = useRef<Target[]>([]);
  useLayoutEffect(() => {
    // Local icons can wrap a new result row. Fit it before the browser paints.
    (window as typeof window & { LandPPTEditorEngine?: { call(name: string): void } }).LandPPTEditorEngine?.call('refreshQuickAiPopoverLayout');
  }, [targets]);
  useLayoutEffect(() => {
    let queued = false, disposed = false;
    function sync() {
      queued = false; if (disposed) return;
      const next: Target[] = [];
      function add(selector: string, Icon: Icon) {
        const node = document.querySelector<HTMLElement>(selector);
        if (node) next.push({ node, Icon, key: selector });
      }
      toolbarIcons.forEach(([action, Icon]) => add(`#quickEditToolbar [onclick="${action}()"] i`, Icon));
      add('.quick-ai-edit-popover-title i', RobotOutlined);
      add('#quickAiVisionToggleBtn i', EyeOutlined);
      add('#quickAiEditPopoverMinBtn i', document.getElementById('quickAiEditPopoverMinBtn')?.title === '还原' ? ExpandOutlined : MinusOutlined);
      add('.quick-ai-edit-popover-close i', CloseOutlined);
      document.querySelectorAll<HTMLElement>('#quickAiEditResult button i').forEach((node, index) => {
        const key = Object.keys(resultIcons).find(key => node.classList.contains(key));
        if (key) next.push({ node, Icon: resultIcons[key as keyof typeof resultIcons], key: `result-${index}` });
      });
      if (next.length === previous.current.length && next.every((item, index) => item.node === previous.current[index].node && item.Icon === previous.current[index].Icon)) return;
      previous.current.forEach(item => { if (!next.some(next => next.node === item.node)) item.node.classList.remove('editor-ant-native-icon'); });
      next.forEach(item => item.node.classList.add('editor-ant-native-icon'));
      previous.current = next; setTargets(next);
    }
    const observer = new MutationObserver(() => { if (!queued) { queued = true; queueMicrotask(sync); } });
    ['quickEditToolbar', 'quickAiEditPopover'].forEach(id => {
      const root = document.getElementById(id);
      if (root) observer.observe(root, { childList: true, subtree: true, attributes: true, attributeFilter: ['title'] });
    });
    sync();
    return () => { disposed = true; observer.disconnect(); previous.current.forEach(item => item.node.classList.remove('editor-ant-native-icon')); };
  }, []);
  return <>{targets.map(({ node, Icon, key }) => createPortal(<Icon aria-hidden />, node, key))}</>;
}
