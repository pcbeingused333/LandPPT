import type { ReactNode, KeyboardEvent } from 'react';

// The browser may move focus to its chrome when Tab leaves the last control.
// Keep that boundary explicit while Ant Design handles popup and modal focus.
export function modalFocus(node: ReactNode) {
  function cycle(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== 'Tab' || !event.currentTarget.contains(document.activeElement)) return;
    const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button,a[href],input,select,textarea,[tabindex]'))
      .filter(element => element.tabIndex >= 0 && !element.matches(':disabled') && element.getClientRects().length > 0 && !element.closest('[aria-hidden="true"]'));
    const destination = event.shiftKey && document.activeElement === controls[0] ? controls.at(-1) : !event.shiftKey && document.activeElement === controls.at(-1) ? controls[0] : undefined;
    if (destination) { event.preventDefault(); destination.focus(); }
  }
  return <div onKeyDownCapture={cycle}>{node}</div>;
}
