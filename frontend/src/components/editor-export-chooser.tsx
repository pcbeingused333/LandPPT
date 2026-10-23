import { useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Card, Drawer, Empty, Flex, Radio, Space, Tag, Typography } from 'antd';
import { DownloadOutlined, EditOutlined, FilePdfOutlined, Html5Outlined, PictureOutlined } from '@ant-design/icons';
import { modalFocus } from './modal-focus';

type Goal = 'edit' | 'faithful' | 'pdf' | 'web';
type Method = { key: string; label: string; description: string; command: string; args?: string[] };
type Props = {
  projectTitle: string; count: number; client: boolean; native: boolean; vector: boolean; standard: boolean;
  saving: boolean; run: (command: string, ...args: string[]) => unknown;
};
const goals = [
  { key: 'edit' as const, label: '继续编辑', icon: <EditOutlined aria-hidden /> },
  { key: 'faithful' as const, label: '保留版式', icon: <PictureOutlined aria-hidden /> },
  { key: 'pdf' as const, label: '阅读打印', icon: <FilePdfOutlined aria-hidden /> },
  { key: 'web' as const, label: '网页演示', icon: <Html5Outlined aria-hidden /> },
];

// Visibility follows the same native capabilities and server permission as the
// former menu. Selection alone must never load a converter or start a request.
export function EditorExportChooser({ projectTitle, count, client, native, vector, standard, saving, run }: Props) {
  const { message } = App.useApp();
  const [open, setOpen] = useState(false), [pending, setPending] = useState(false);
  const [goal, setGoal] = useState<Goal>('edit'), [choices, setChoices] = useState<Partial<Record<Goal, string>>>({});
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
  const options: Record<Goal, Method[]> = {
    edit: [
      ...(native ? [{ key: 'native', label: 'SVG 原生对象 PPTX', description: '文字和支持的图形转换为 PowerPoint 对象，复杂效果可能有所不同。', command: 'exportSvgPagesToPptx', args: ['native'] }] : []),
      ...(client ? [{ key: 'client', label: '客户端导出 PPTX · Beta', description: '将页面中的文字和支持的图形转换为可编辑对象，复杂布局建议另存保真版本。', command: 'exportSlidesToPptxClient' }] : []),
      ...(standard ? [{ key: 'standard', label: '标准导出 PPTX', description: '使用原有兼容转换方式，元素的可编辑程度取决于页面结构。', command: 'exportToPPTX' }] : []),
    ],
    faithful: [
      ...(vector ? [{ key: 'vector', label: 'SVG 矢量保真 PPTX', description: '每页保留为完整 SVG 图层，支持缩放；文字和图形不拆分为独立对象。', command: 'exportSvgPagesToPptx', args: ['vector'] }] : []),
      { key: 'images', label: '图片形式 PPTX', description: '每页渲染为一张图片，优先保留外观；页内文字和图形不能单独编辑。', command: 'exportToPPTXAsImages' },
    ],
    pdf: [{ key: 'pdf', label: '导出 PDF', description: '适合阅读、分发与打印，完成后下载整份文稿的 PDF 文件。', command: 'exportToPDF' }],
    web: [{ key: 'html', label: '下载 HTML', description: '下载 HTML 文件包（ZIP），解压后使用浏览器打开演示页面。', command: 'downloadHTML' }],
  };
  const methods = options[goal], method = methods.find(item => item.key === choices[goal]) || methods[0];
  const format = goal === 'pdf' ? 'PDF' : goal === 'web' ? 'ZIP' : 'PPTX';
  const changedCapability = !!choices[goal] && !methods.some(item => item.key === choices[goal]);
  async function start() {
    if (locked.current || saving || !count || !method) return;
    locked.current = true; setPending(true); setOpen(false);
    // The drawer closes instantly, so the second click of a double-click would land on the AI rail beneath it.
    const shield = (event: MouseEvent) => { if (event.detail > 1) { event.preventDefault(); event.stopPropagation(); } };
    document.addEventListener('click', shield, true); window.setTimeout(() => document.removeEventListener('click', shield, true), 500);
    try { await run(method.command, ...method.args || []); }
    catch (error) { void message.error((error as Error).message || '无法启动导出，请重试'); }
    finally { locked.current = false; completed.current = true; setPending(false); }
  }
  return <>
    <Button ref={trigger} data-editor-export-trigger title="导出" disabled={!count || pending} icon={<DownloadOutlined aria-hidden />} onClick={() => setOpen(true)}>导出</Button>
    <Drawer title="导出演示文稿" open={open} onClose={() => setOpen(false)} size={560} zIndex={1700} className="editor-export-chooser" styles={{ wrapper: { maxWidth: '100vw' } }}
      afterOpenChange={value => { if (!value && !document.querySelector('.editor-ant-dialog') && trigger.current?.isConnected) trigger.current.focus({ preventScroll: true }); }}
      drawerRender={node => <div style={{ height: '100%' }} onKeyDown={event => { event.stopPropagation(); if (event.key === 'Escape') { event.preventDefault(); setOpen(false); } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') event.preventDefault(); }}>{modalFocus(node, { height: '100%' })}</div>}
      footer={<Flex justify="space-between" align="center" gap={8} wrap><Typography.Text type="secondary">{count} 页 · {format}</Typography.Text><Space><Button onClick={() => setOpen(false)}>取消</Button><Button type="primary" icon={<DownloadOutlined aria-hidden />} disabled={!count || !method || saving || pending} onClick={() => void start()}>开始导出</Button></Space></Flex>}>
      <Space orientation="vertical" size="middle" className="editor-export-chooser-body">
        <Flex align="center" justify="space-between" gap={12}><Typography.Text strong ellipsis title={projectTitle}>{projectTitle || '演示文稿'}</Typography.Text><Tag>{format}</Tag></Flex>
        <Typography.Paragraph type="secondary" style={{ margin: 0 }}>导出整份文稿，共 {count} 页。导出前请先保存页面和讲稿修改。</Typography.Paragraph>
        {saving && <Alert showIcon type="info" title="正在保存，完成后即可导出。" />}
        <section aria-label="导出用途" className="editor-export-goals">{goals.map(item => <Button key={item.key} type={goal === item.key ? 'primary' : 'default'} aria-pressed={goal === item.key} icon={item.icon} onClick={() => setGoal(item.key)}>{item.label}</Button>)}</section>
        <Card size="small" title="导出方式">
          {changedCapability && <Alert showIcon type="info" title="页面模式已变化，请确认当前可用的导出方式。" style={{ marginBottom: 16 }} />}
          {!methods.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前页面暂不支持此方式，请选择其他用途。" /> : <Radio.Group value={method.key} className="editor-export-methods" onChange={event => setChoices(current => ({ ...current, [goal]: event.target.value }))}>
            <Space orientation="vertical" size="middle">{methods.map(item => <Radio key={item.key} value={item.key} aria-label={item.label}><Space orientation="vertical" size={4}><Typography.Text strong>{item.label}</Typography.Text><Typography.Text type="secondary">{item.description}</Typography.Text></Space></Radio>)}</Space>
          </Radio.Group>}
        </Card>
        <Typography.Text type="secondary">单页导出可在左侧幻灯片的右键菜单中选择，也可按 Shift+F10 打开。</Typography.Text>
      </Space>
    </Drawer>
  </>;
}
