import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { App, Button, Descriptions, Drawer, Dropdown, Modal, Result, Select, Spin, Tooltip } from 'antd';
import { LeftOutlined, RightOutlined, PlayCircleOutlined, PauseOutlined, FullscreenOutlined, FullscreenExitOutlined, CloseOutlined, AppstoreOutlined, EllipsisOutlined, SoundOutlined, StopOutlined } from '@ant-design/icons';
import type { ApiData } from '../api';
import { modalFocus } from '../components/modal-focus';

type Panel = 'slides' | 'keys' | 'cache' | null;
type State = { index: number; slides: ApiData[]; total: number; autoPlaying: boolean; fullscreen: boolean; narration: boolean; language: string; subtitle: string; panel: Panel; uiHidden: boolean; loading: boolean; transitioning: boolean; cache: { cachedSlides: number; loadingSlides: number; totalSlides: number; cacheRatio: string } };
type Controller = { getState(): State; previousSlide(): void; nextSlide(): void; goToSlide(index: number): void; toggleAutoPlay(): void; toggleFullscreen(): void; toggleNarration(): void; changeLanguage(language: string): void; toggleThumbnails(): void; toggleKeyboardHints(): void; toggleCacheStatus(): void; setPanel(panel: Panel): void; exitPresentation(): void; holdUi(hold: boolean): void; revealUiTemporarily(): void; getSlideFrameBaseSize(frame: HTMLIFrameElement): { width: number; height: number } };
const getController = () => (window as typeof window & { LandPPTPresentation?: Controller }).LandPPTPresentation;
const shortcuts = [['上一页', '←'], ['下一页', '→ / Space'], ['首 / 末页', 'Home / End'], ['全屏', 'F'], ['页面缩略图', 'T'], ['讲解', 'N'], ['快捷键', 'H'], ['缓存状态', 'C'], ['退出面板 / 全屏 / 演示', 'Esc']];

function Thumbnail({ slide, controller }: { slide: ApiData; controller: Controller }) {
  const frame = useRef<HTMLIFrameElement>(null);
  const preview = useRef<HTMLSpanElement>(null);
  const fit = () => {
    if (!frame.current || !preview.current) return;
    const base = controller.getSlideFrameBaseSize(frame.current);
    const scale = Math.min(preview.current.clientWidth / base.width, preview.current.clientHeight / base.height);
    Object.assign(frame.current.style, { width: `${base.width}px`, height: `${base.height}px`, transform: `scale(${scale})` });
  };
  useEffect(() => {
    if (!preview.current) return;
    const observer = new ResizeObserver(fit);
    observer.observe(preview.current);
    return () => observer.disconnect();
  }, [slide.html_content]);
  return <span ref={preview} className="presentation-thumbnail-preview"><iframe ref={frame} srcDoc={slide.html_content || ''} title="缩略图预览" tabIndex={-1} aria-hidden onLoad={fit} /></span>;
}

export default function Presentation({ data }: { data: ApiData }) {
  const controller = getController();
  const [state, setState] = useState(() => controller?.getState());
  const origin = useRef<HTMLElement | null>(null);
  const previousPanel = useRef<Panel>(null);
  const moreButton = useRef<HTMLButtonElement>(null);
  const { message } = App.useApp();
  useEffect(() => {
    const update = (event: Event) => {
      const next = (event as CustomEvent<State>).detail;
      if (next.panel && !previousPanel.current) origin.current = document.activeElement?.closest('.ant-dropdown') ? moreButton.current : document.activeElement as HTMLElement;
      previousPanel.current = next.panel;
      setState(next);
    };
    const notify = (event: Event) => {
      const detail = (event as CustomEvent<{ message: string; type: 'info' | 'success' | 'warning' | 'error' }>).detail;
      message.open({ type: detail.type, content: detail.message });
    };
    window.addEventListener('landppt:presentation-state', update);
    window.addEventListener('landppt:presentation-message', notify);
    setState(getController()?.getState());
    return () => { window.removeEventListener('landppt:presentation-state', update); window.removeEventListener('landppt:presentation-message', notify); };
  }, [message]);
  if (!controller || !state) return <Result status="error" title="放映控件加载失败" extra={<Button onClick={() => location.reload()}>重新加载</Button>} />;
  const restoreFocus = (open: boolean) => {
    if (!open && origin.current?.isConnected) { origin.current.focus(); controller.revealUiTemporarily(); }
  };
  const iconButton = (label: string, icon: React.ReactNode, action: () => void, disabled = false, active = false) => <Tooltip title={label}><Button type={active ? 'primary' : 'default'} aria-label={label} icon={icon} onClick={action} disabled={disabled} /></Tooltip>;
  const holdProps = { onMouseEnter: () => controller.holdUi(true), onMouseLeave: () => controller.holdUi(false), onFocusCapture: () => controller.revealUiTemporarily() };
  const loadingTarget = document.getElementById('loadingOverlay');
  if (!state.total) return <div className="presentation-empty"><Result status="info" title="暂无可放映的页面" subTitle="请在项目中完成生成或添加幻灯片后再打开演示。" extra={<Button onClick={controller.exitPresentation}>退出演示</Button>} /></div>;
  return <>
    <div className="presentation-ui" aria-hidden={state.uiHidden} inert={state.uiHidden}>
      <header className="presentation-toolbar presentation-topbar" {...holdProps}><div className="presentation-title-block"><span>{data.isShared ? '分享演示' : '演示放映'} · {state.total} 页</span><h1 title={data.title}>{data.title}</h1></div>{iconButton('页面缩略图', <AppstoreOutlined aria-hidden />, controller.toggleThumbnails)}<Dropdown trigger={['click']} onOpenChange={open => { controller.holdUi(open); if (!open && !controller.getState().panel) queueMicrotask(() => moreButton.current?.focus()); }} menu={{ items: [{ key: 'keys', label: '快捷键' }, { key: 'cache', label: '缓存状态' }], onClick: ({ key }) => controller.setPanel(key as Panel) }}><Button ref={moreButton} aria-label="更多操作" icon={<EllipsisOutlined aria-hidden />} /></Dropdown>{iconButton('退出演示', <CloseOutlined aria-hidden />, controller.exitPresentation)}</header>
      <nav className="presentation-toolbar presentation-bottom-bar" aria-label="放映操作" {...holdProps}>
        <div className="presentation-navigation">{iconButton('上一页', <LeftOutlined aria-hidden />, controller.previousSlide, state.index === 0 || state.transitioning)}<span className="presentation-counter" role="status" aria-label="当前页">{state.index + 1} / {state.total}</span>{iconButton('下一页', <RightOutlined aria-hidden />, controller.nextSlide, state.index === state.total - 1 || state.transitioning)}{iconButton(state.autoPlaying ? '暂停自动播放' : '自动播放', state.autoPlaying ? <PauseOutlined aria-hidden /> : <PlayCircleOutlined aria-hidden />, controller.toggleAutoPlay, !state.autoPlaying && state.index === state.total - 1, state.autoPlaying)}{iconButton(state.fullscreen ? '退出全屏' : '全屏', state.fullscreen ? <FullscreenExitOutlined aria-hidden /> : <FullscreenOutlined aria-hidden />, controller.toggleFullscreen)}</div>
        {data.hasSpeechScripts && <div className="presentation-narration"><Select aria-label="讲解语言" value={state.language} onChange={controller.changeLanguage} onOpenChange={open => controller.holdUi(open)} options={[{ value: 'zh', label: '中文', disabled: !data.narrationLanguages.includes('zh') }, { value: 'en', label: 'English', disabled: !data.narrationLanguages.includes('en') }]} getPopupContainer={node => node.parentElement!} /><Button type={state.narration ? 'primary' : 'default'} aria-label={state.narration ? '停止讲解' : '讲解'} icon={state.narration ? <StopOutlined aria-hidden /> : <SoundOutlined aria-hidden />} onClick={controller.toggleNarration}>{state.narration ? '停止讲解' : '讲解'}</Button></div>}
      </nav>
    </div>
    {state.subtitle && <div className="presentation-subtitle" role="status" aria-live="polite" aria-label="讲解字幕">{state.subtitle}</div>}
    {loadingTarget && state.loading && createPortal(<Spin size="large" aria-label="正在加载幻灯片" />, loadingTarget)}
    <Drawer title="页面缩略图" placement="left" size={280} open={state.panel === 'slides'} onClose={() => controller.setPanel(null)} afterOpenChange={restoreFocus} drawerRender={modalFocus} className="presentation-panel" destroyOnHidden>
      <div className="presentation-thumbnails">{state.slides.map((slide, index) => <Button key={index} className="presentation-thumbnail" aria-label={`第 ${index + 1} 页：${slide.title || '未命名页面'}`} aria-current={index === state.index ? 'page' : undefined} disabled={state.transitioning} onClick={() => { controller.goToSlide(index); controller.setPanel(null); }}><Thumbnail slide={slide} controller={controller} /><span className="presentation-thumbnail-label">{index + 1} · {slide.title || '未命名页面'}</span></Button>)}</div>
    </Drawer>
    <Modal title="快捷键" open={state.panel === 'keys'} footer={null} onCancel={() => controller.setPanel(null)} afterOpenChange={restoreFocus} modalRender={modalFocus} className="presentation-panel" width={400}><dl className="presentation-shortcuts">{shortcuts.map(([label, key]) => <div key={key}><dt>{label}</dt><dd><kbd>{key}</kbd></dd></div>)}</dl></Modal>
    <Modal title="缓存状态" open={state.panel === 'cache'} footer={null} onCancel={() => controller.setPanel(null)} afterOpenChange={restoreFocus} modalRender={modalFocus} className="presentation-panel" width={360}><Descriptions column={1} size="small" items={[{ key: 'cached', label: '已缓存', children: `${state.cache.cachedSlides} 页` }, { key: 'loading', label: '加载中', children: `${state.cache.loadingSlides} 页` }, { key: 'total', label: '总页数', children: `${state.cache.totalSlides} 页` }, { key: 'ratio', label: '缓存比例', children: state.cache.cacheRatio }]} /></Modal>
  </>;
}
