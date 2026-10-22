import type { OutlineStream } from './outline-controller';

type Renderer = { setText(text: string): void; destroy(): void };

// Own only the supplied preview node; reading/stream state stays in the controller.
export function createOutlineStreamView(node: HTMLDivElement, jump: HTMLButtonElement) {
  let destroyed = false, sticky = true, lastTop = 0, currentRun = -1;
  let text = '', frame: number | null = null, settleFrame: number | null = null;
  let renderer: Renderer | null = null, loading = false;
  function chrome() { jump.hidden = sticky; }
  function bottom() {
    if (destroyed || !sticky) return;
    node.scrollTop = Math.max(0, node.scrollHeight - node.clientHeight);
    lastTop = node.scrollTop;
  }
  function paint() {
    frame = null;
    if (destroyed) return;
    if (renderer) renderer.setText(text); else node.textContent = text;
    if (!renderer && !loading && text) {
      loading = true;
      const path = '/static/js/pages/project/todo_board/outlineStreamPretextRenderer.js?v=20260404-pretext';
      import(/* @vite-ignore */ path).then(module => {
        if (destroyed) return;
        renderer = module.createOutlineStreamPretextRenderer(node);
        schedule();
      }).catch(() => { /* Plain text remains available when the renderer fails. */ });
    }
    if (settleFrame !== null) cancelAnimationFrame(settleFrame);
    settleFrame = requestAnimationFrame(() => { settleFrame = null; bottom(); });
    chrome();
  }
  function schedule() { if (frame === null && !destroyed) frame = requestAnimationFrame(paint); }
  function nearBottom() { return node.scrollHeight - node.clientHeight - node.scrollTop <= 28; }
  function scroll() {
    if (node.scrollTop < lastTop - 2) sticky = false;
    else if (nearBottom()) sticky = true;
    lastTop = node.scrollTop; chrome();
  }
  function wheel(event: WheelEvent) {
    if (node.scrollHeight <= node.clientHeight) return;
    const next = Math.min(Math.max(0, node.scrollHeight - node.clientHeight), Math.max(0, node.scrollTop + event.deltaY));
    if (next === node.scrollTop) return;
    event.preventDefault(); event.stopPropagation();
    if (event.deltaY < 0) sticky = false;
    node.scrollTop = next; lastTop = next;
    if (event.deltaY > 0 && nearBottom()) sticky = true;
    chrome();
  }
  function latest() { sticky = true; bottom(); chrome(); schedule(); }
  node.tabIndex = 0;
  node.addEventListener('scroll', scroll);
  node.addEventListener('wheel', wheel, { passive: false });
  jump.addEventListener('click', latest);
  return {
    setStream(value: OutlineStream) {
      if (destroyed) return;
      if (value.run !== currentRun) { currentRun = value.run; sticky = true; lastTop = 0; }
      text = value.text; schedule();
    },
    destroy() {
      destroyed = true;
      if (frame !== null) cancelAnimationFrame(frame);
      if (settleFrame !== null) cancelAnimationFrame(settleFrame);
      renderer?.destroy();
      node.removeEventListener('scroll', scroll); node.removeEventListener('wheel', wheel);
      jump.removeEventListener('click', latest);
    },
  };
}
