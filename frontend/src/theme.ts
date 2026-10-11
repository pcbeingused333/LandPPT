import { theme, type ThemeConfig } from 'antd';

export const landpptTheme: ThemeConfig = {
  algorithm: theme.defaultAlgorithm,
  token: {
    colorPrimary: '#111111', colorInfo: '#111111', colorLink: '#111111',
    colorPrimaryBg: '#f2f2f2', colorPrimaryBorder: '#dedede',
    colorInfoBg: '#f2f2f2', colorInfoBorder: '#dedede', colorInfoText: '#252936',
    colorText: '#252936', colorTextSecondary: '#6b7280',
    colorBgLayout: '#f5f5f7', colorBgContainer: '#ffffff', colorBorder: '#dedede',
    fontSize: 14, borderRadius: 6, controlHeight: 32, motion: false,
    fontFamily: '"PingFang SC", "Microsoft YaHei", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  },
  components: {
    Button: { primaryShadow: 'none', defaultShadow: 'none' },
    Card: { borderRadiusLG: 8 },
    Tabs: { horizontalItemGutter: 24 },
  },
};
