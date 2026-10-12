import { useEffect } from 'react';
import { App } from 'antd';
import { modalFocus } from './modal-focus';

// Native outline/generation controllers keep their existing notification API.
// Ant Design owns the visible messages and confirmations on migrated pages.
export function useNativeFeedback() {
  const { modal, message } = App.useApp();
  useEffect(() => {
    const target = window as typeof window & { Notify?: Record<string, any> };
    const previous = target.Notify;
    const bridge = { ...previous,
      toast: (text: string, options?: { type?: 'success' | 'info' | 'warning' | 'error'; duration?: number }) => message.open({ type: options?.type || 'info', content: String(text), ...(options?.duration == null ? {} : { duration: options.duration / 1000 }) }),
      ...Object.fromEntries((['success', 'info', 'warning', 'error'] as const).map(type => [type, (text: string) => message.open({ type, content: String(text) })])),
      confirm: (text: string, options?: { danger?: boolean }) => new Promise<boolean>(resolve => {
        modal.confirm({ title: '操作确认', zIndex: document.body.classList.contains('landppt-editor') ? 6000 : undefined, content: <p className="generator-confirm-text">{String(text)}</p>, okText: '确认', cancelText: '取消', okButtonProps: { danger: options?.danger }, modalRender: modalFocus, onOk: () => resolve(true), onCancel: () => resolve(false) });
      }),
    };
    target.Notify = bridge;
    return () => { if (target.Notify === bridge) target.Notify = previous; };
  }, [message, modal]);
}
