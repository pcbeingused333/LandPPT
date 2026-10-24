import { useEffect, useRef, useState } from 'react';
import { App, Button, Dropdown, type MenuProps } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';

type Method = { key: string; label: string; description: string; command: string; args?: string[] };
type Props = {
  projectTitle: string; count: number; client: boolean; native: boolean; vector: boolean; standard: boolean;
  saving: boolean; run: (command: string, ...args: string[]) => unknown;
};

// Visibility follows the same native capabilities and server permission as the
// former chooser. Opening the menu never loads a converter or starts a request.
export function EditorExportChooser({ projectTitle, count, client, native, vector, standard, saving, run }: Props) {
  const { message } = App.useApp();
  const [open, setOpen] = useState(false), [pending, setPending] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null), locked = useRef(false);
  const completed = useRef(false);
  useEffect(() => {
    if (pending || !completed.current) return;
    completed.current = false;
    const active = document.activeElement;
    // The progress dialog may finish while this trigger is still disabled.
    // Restore it after React enables it, without stealing focus from ongoing work.
    if (!open && !document.querySelector('.editor-ant-dialog') && (!active || active === document.body || !active.getClientRects().length)) trigger.current?.focus({ preventScroll: true });
  }, [open, pending]);
  const groups: { key: string; label: string; methods: Method[] }[] = [
    { key: 'edit', label: '可编辑 PPTX', methods: [
      ...(native ? [{ key: 'native', label: 'SVG 原生对象 PPTX', description: '文字和图形转为 PowerPoint 对象', command: 'exportSvgPagesToPptx', args: ['native'] }] : []),
      ...(client ? [{ key: 'client', label: '客户端导出 PPTX · Beta', description: '文字和支持的图形可单独编辑', command: 'exportSlidesToPptxClient' }] : []),
      ...(standard ? [{ key: 'standard', label: '标准导出 PPTX', description: '原有兼容转换方式', command: 'exportToPPTX' }] : []),
    ] },
    { key: 'faithful', label: '保留版式', methods: [
      ...(vector ? [{ key: 'vector', label: 'SVG 矢量保真 PPTX', description: '每页一个完整 SVG 图层', command: 'exportSvgPagesToPptx', args: ['vector'] }] : []),
      { key: 'images', label: '图片形式 PPTX', description: '每页一张图片，页内文字和图形不能单独编辑', command: 'exportToPPTXAsImages' },
    ] },
    { key: 'other', label: '阅读与分享', methods: [
      { key: 'pdf', label: '导出 PDF', description: '适合阅读、分发与打印', command: 'exportToPDF' },
      { key: 'html', label: '下载 HTML', description: 'HTML 文件包（ZIP），解压后用浏览器打开', command: 'downloadHTML' },
    ] },
  ];
  const methods = new Map(groups.flatMap(group => group.methods.map(item => [item.key, item] as const)));
  async function start(method: Method) {
    if (locked.current || saving || !count) return;
    locked.current = true; setPending(true); setOpen(false);
    // The menu closes instantly, so the second click of a double-click would land on the canvas beneath it.
    const shield = (event: MouseEvent) => { if (event.detail > 1) { event.preventDefault(); event.stopPropagation(); } };
    document.addEventListener('click', shield, true); window.setTimeout(() => document.removeEventListener('click', shield, true), 500);
    try { await run(method.command, ...method.args || []); }
    catch (error) { void message.error((error as Error).message || '无法启动导出，请重试'); }
    finally { locked.current = false; completed.current = true; setPending(false); }
  }
  const items: MenuProps['items'] = [
    { key: 'summary', type: 'group', label: <span className="editor-export-summary" title={projectTitle}>{saving ? '正在保存，完成后即可导出' : `导出整份文稿 · ${count} 页`}</span> },
    ...groups.filter(group => group.methods.length).map(group => ({
      key: group.key, type: 'group' as const, label: group.label,
      children: group.methods.map(item => ({ key: item.key, disabled: saving, label: <span className="editor-export-item"><span>{item.label}</span><small>{item.description}</small></span> })),
    })),
    { type: 'divider' },
    { key: 'hint', type: 'group', label: <span className="editor-export-hint">单页导出：右键左侧幻灯片，或按 Shift+F10</span> },
  ];
  return <Dropdown trigger={['click']} open={open} placement="bottomRight" classNames={{ root: 'editor-export-menu' }}
    onOpenChange={(value, info) => { if (info.source === 'trigger' || !value) setOpen(value); if (!value) queueMicrotask(() => { if (!locked.current && !document.querySelector('.editor-ant-dialog')) trigger.current?.focus({ preventScroll: true }); }); }}
    menu={{ items, onClick: ({ key }) => { const method = methods.get(key); if (method) void start(method); } }}>
    <Button ref={trigger} data-editor-export-trigger title="导出" aria-haspopup="menu" aria-expanded={open} disabled={!count || pending} icon={<DownloadOutlined aria-hidden />}>导出</Button>
  </Dropdown>;
}
