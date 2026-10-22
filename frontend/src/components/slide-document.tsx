import { memo, useLayoutEffect, useRef } from 'react';
import './slide-document.css';

// Scale the original document from outside its frame. Application styles never
// rewrite presentation HTML, and ordinary status updates keep the frame alive.
export const SlideDocument = memo(function SlideDocument({ html, title, interactive = false, contain = false, onKeyDown }: {
  html: string; title: string; interactive?: boolean; contain?: boolean;
  onKeyDown?: (event: KeyboardEvent) => void;
}) {
  const root = useRef<HTMLDivElement>(null);
  const frame = useRef<HTMLIFrameElement>(null);
  const keyboard = useRef(onKeyDown); keyboard.current = onKeyDown;
  const detach = useRef<() => void>(() => {});
  const resize = () => {
    if (!root.current || !frame.current) return;
    const scale = Math.min(root.current.clientWidth / 1280, root.current.clientHeight / 720);
    frame.current.style.transform = `scale(${scale})`;
  };
  const loaded = () => {
    resize(); detach.current();
    // A document can navigate itself away from this origin. It remains viewable,
    // but cannot share keyboard events with the application after that point.
    try {
      const document = frame.current?.contentDocument;
      const handle = (event: KeyboardEvent) => keyboard.current?.(event);
      document?.addEventListener('keydown', handle);
      detach.current = () => document?.removeEventListener('keydown', handle);
    } catch { detach.current = () => {}; }
  };
  useLayoutEffect(() => {
    const observer = new ResizeObserver(resize);
    if (root.current) observer.observe(root.current);
    resize();
    return () => { observer.disconnect(); detach.current(); };
  }, []);
  return <div ref={root} className={`slide-document${contain ? ' is-contained' : ''}${interactive ? ' is-interactive' : ''}`}>
    <iframe ref={frame} title={title} srcDoc={html} tabIndex={interactive ? 0 : -1} onLoad={loaded} />
  </div>;
});
