import { theme, type ThemeConfig } from 'antd';

// Resolve the shared Jinja/native palette before React mounts.
const palette = getComputedStyle(document.documentElement);
const color = (name: string) => palette.getPropertyValue(`--lp-${name}`).trim();

export const landpptTheme: ThemeConfig = {
  algorithm: document.documentElement.dataset.theme === 'light' ? theme.defaultAlgorithm : theme.darkAlgorithm,
  cssVar: { key: 'landppt' },
  token: {
    colorPrimary: color('primary'), colorInfo: color('info'), colorLink: color('text'),
    colorSuccess: color('success'), colorWarning: color('accent'), colorError: color('danger'),
    colorText: color('text'), colorTextSecondary: color('secondary'), colorTextTertiary: color('muted'),
    colorTextPlaceholder: color('muted'), colorTextDisabled: color('disabled'),
    colorBgLayout: color('bg'), colorBgContainer: color('surface'), colorBgElevated: color('elevated'),
    colorBorder: color('border'), colorBorderSecondary: color('border'), colorBgMask: color('mask'),
    colorTextLightSolid: color('on-primary'),
    // One compact control scale (32/26px) across app pages, the workspace and the editor toolbar.
    fontSize: 14, borderRadius: 10, borderRadiusLG: 16, controlHeight: 32, controlHeightSM: 26, controlHeightLG: 40, motion: false,
    fontFamily: palette.getPropertyValue('--lp-font').trim(),
    boxShadow: 'none', boxShadowSecondary: 'none',
  },
  components: {
    Button: { fontWeight: 500, borderRadius: 999, contentFontSize: 13, paddingInline: 14, paddingInlineSM: 10, primaryColor: color('on-primary'), primaryShadow: 'none', defaultShadow: 'none', defaultHoverBg: color('hover'), defaultHoverBorderColor: color('border-strong'), colorPrimary: color('primary'), colorPrimaryHover: color('text'), colorPrimaryActive: color('secondary') },
    Card: { borderRadiusLG: 16, headerBg: 'transparent', headerHeight: 44, headerHeightSM: 36, bodyPadding: 16, headerPadding: 16, headerFontSize: 14 },
    Input: { colorBgContainer: color('elevated'), activeShadow: 'none', activeBorderColor: color('border-strong'), hoverBorderColor: color('border-strong') },
    Select: { optionSelectedBg: color('hover'), optionSelectedColor: color('text'), optionActiveBg: color('hover'), controlItemBgActiveHover: color('border'), activeBorderColor: color('border-strong'), activeOutlineColor: 'transparent' },
    Segmented: { trackBg: color('bg'), itemSelectedBg: color('hover'), itemSelectedColor: color('text') },
    Tabs: { horizontalItemGutter: 20, horizontalItemPadding: '8px 0', titleFontSize: 13 },
    Modal: { contentBg: color('surface'), headerBg: color('surface') },
    Drawer: { colorBgElevated: color('surface') },
    Tooltip: { colorBgSpotlight: color('hover'), colorTextLightSolid: color('text') },
  },
};
