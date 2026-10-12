import { theme, type ThemeConfig } from 'antd';

export const landpptTheme: ThemeConfig = {
  algorithm: theme.defaultAlgorithm,
  token: {
    colorPrimary: '#111111', colorInfo: '#111111', colorLink: '#111111',
    colorPrimaryBg: '#f2f2f2', colorPrimaryBorder: '#dedede',
    colorInfoBg: '#f2f2f2', colorInfoBorder: '#dedede', colorInfoText: '#252936',
    colorText: '#252936', colorTextSecondary: '#6b7280',
    colorBgLayout: '#f5f5f7', colorBgContainer: '#ffffff', colorBorder: '#dedede',
    fontSize: 14, borderRadius: 8, controlHeight: 32, motion: false,
    fontFamily: '"PingFang SC", "Microsoft YaHei", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  },
  components: {
    Button: { fontWeight: 500, primaryShadow: '0 1px 2px #00000020', defaultShadow: '0 1px 2px #00000005', defaultHoverBg: '#f7f7f8', defaultHoverBorderColor: '#a1a1aa' },
    Card: { borderRadiusLG: 10, headerBg: '#fcfcfd' },
    Select: {
      optionSelectedBg: '#f0f0f0', optionSelectedColor: '#111111',
      optionActiveBg: '#f7f7f7', controlItemBgActiveHover: '#e8e8e8',
    },
    Tabs: { horizontalItemGutter: 24 },
  },
};
