import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Button, ConfigProvider, Tooltip } from 'antd';
import { MoonOutlined, SunOutlined } from '@ant-design/icons';
import zhCN from 'antd/locale/zh_CN';
import { applyAppearance, appearanceStorageKey, buildTheme, currentAppearance, storedAppearance, type Appearance } from '../theme';

const AppearanceContext = createContext<{ mode: Appearance; toggle(): void }>({ mode: 'dark', toggle() {} });

// Owns the dark / 可可蛋白 choice: native CSS follows the <html> attribute and
// Ant tokens are rebuilt from the same design-tokens.css values.
export function AppearanceProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<Appearance>(currentAppearance);
  useEffect(() => {
    const sync = (event: StorageEvent) => {
      if (event.key !== appearanceStorageKey) return;
      const next = storedAppearance(event.newValue);
      applyAppearance(next); setMode(next);
    };
    addEventListener('storage', sync);
    return () => removeEventListener('storage', sync);
  }, []);
  const theme = useMemo(() => buildTheme(mode), [mode]);
  const value = useMemo(() => ({ mode, toggle() { const next = mode === 'light' ? 'dark' : 'light'; applyAppearance(next); setMode(next); } }), [mode]);
  return <AppearanceContext.Provider value={value}><ConfigProvider locale={zhCN} theme={theme} button={{ autoInsertSpace: false }}>{children}</ConfigProvider></AppearanceContext.Provider>;
}

export function AppearanceToggle({ className }: { className?: string }) {
  const { mode, toggle } = useContext(AppearanceContext);
  const label = mode === 'light' ? '切换到深色模式' : '切换到浅色模式（可可蛋白）';
  return <Tooltip title={label}><Button type="text" className={className} aria-label={label} aria-pressed={mode === 'light'} icon={mode === 'light' ? <MoonOutlined aria-hidden /> : <SunOutlined aria-hidden />} onClick={toggle} /></Tooltip>;
}
