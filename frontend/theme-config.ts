/**
 * Element Plus 主题配置
 * 基于 AdminCore 设计规范：青色 (Teal) + 石板灰 (Slate) + 明暗双主题
 * 参考：./design-spec/02-色彩系统.md
 *
 * 说明：Element Plus 运行时主题通过 CSS 变量 + html.dark 类实现（见 src/styles/），
 * 本文件作为设计令牌的 TS 来源，供构建工具和脚本引用。
 */

// 主题色板（element-plus 未导出 ThemeConfig 类型，这里按实际使用的字段自定义）
export interface ThemePalette {
  colorPrimary: string
  colorSuccess: string
  colorWarning: string
  colorError: string
  colorInfo: string
  colorBgBase: string
  colorBgElevated: string
  colorBgContainer: string
  colorBgContainerDisabled: string
  colorBorder: string
  colorBorderSecondary: string
  textColorPrimary: string
  textColorRegular: string
  textColorSecondary: string
  textColorDisabled: string
  textColorPlaceholder: string
  fillColor: string
  fillColorLight: string
  fillColorLighter: string
  fillColorExtraLight: string
  fillColorDisabled: string
  borderRadius: number
  borderRadiusLarge: number
  boxShadow: string
  boxShadowDark: string
}

export interface ThemeConfig {
  light: ThemePalette
  dark: ThemePalette
}

// 设计规范色值（从 design-spec/02-色彩系统.md 提取）
const designTokens = {
  // 主色（Teal 青色系）
  primary: {
    50: '#f0fdfa',
    100: '#ccfbf1',
    200: '#99f6e4',
    300: '#5eead4',
    400: '#2dd4bf',
    500: '#14b8a6', // 锚点
    600: '#0d9488',
    700: '#0f766e',
    800: '#115e59',
    900: '#134e4a',
    950: '#042f2e',
  },
  // 辅色/暗色（Slate 石板灰系）
  dark: {
    50: '#f8fafc',
    100: '#f1f5f9',
    200: '#e2e8f0',
    300: '#cbd5e1',
    400: '#94a3b8',
    500: '#64748b',
    600: '#475569',
    700: '#334155',
    800: '#1e293b',
    900: '#0f172a',
    950: '#020617',
  },
  // Gray 灰阶（light 模式主力）
  gray: {
    50: '#f9fafb',
    100: '#f3f4f6',
    200: '#e5e7eb',
    300: '#d1d5db',
    400: '#9ca3af',
    500: '#6b7280',
    600: '#4b5563',
    700: '#374151',
    800: '#1f2937',
    900: '#111827',
  },
}

// Light 模式主题配置
export const lightTheme: { light: ThemePalette } = {
  light: {
    // 基础色值
    colorPrimary: designTokens.primary[500], // #14b8a6 - 主色
    colorSuccess: '#10b981', // emerald-500 - 成功
    colorWarning: '#f59e0b', // amber-500 - 警告
    colorError: '#ef4444', // red-500 - 错误
    colorInfo: designTokens.primary[500], // 同主色

    // 背景色
    colorBgBase: '#ffffff', // 基础背景
    colorBgElevated: designTokens.gray[50], // #f9fafb - 页面背景
    colorBgContainer: '#ffffff', // 卡片背景
    colorBgContainerDisabled: designTokens.gray[100], // 禁用背景

    // 边框/分割线
    colorBorder: designTokens.gray[200], // #e5e7eb
    colorBorderSecondary: designTokens.gray[100], // #f3f4f6

    // 文字色
    textColorPrimary: designTokens.gray[900], // #111827 - 主文字
    textColorRegular: designTokens.gray[700], // #374151 - 常规文字
    textColorSecondary: designTokens.gray[500], // #6b7280 - 辅助文字
    textColorDisabled: designTokens.gray[400], // 禁用文字
    textColorPlaceholder: designTokens.gray[400], // placeholder

    // 填充色
    fillColor: designTokens.primary[100], // 浅色填充
    fillColorLight: designTokens.primary[50], // 更浅色填充
    fillColorLighter: designTokens.gray[50], // 最浅色填充
    fillColorExtraLight: designTokens.gray[100],
    fillColorDisabled: designTokens.gray[200],

    // 尺寸
    borderRadius: 12, // 控件圆角
    borderRadiusLarge: 16, // 容器圆角（卡片、弹窗）

    // 阴影
    boxShadow: '0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)',
    boxShadowDark: '0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1)',
  },
}

// Dark 模式主题配置
export const darkTheme: { dark: ThemePalette } = {
  dark: {
    // 基础色值
    colorPrimary: designTokens.primary[500], // #14b8a6 - 主色不变
    colorSuccess: '#10b981', // 成功色
    colorWarning: '#f59e0b', // 警告色
    colorError: '#ef4444', // 错误色
    colorInfo: designTokens.primary[500],

    // 背景色
    colorBgBase: '#000000', // 深色背景
    colorBgElevated: designTokens.dark[950], // #020617 - 页面底色
    colorBgContainer: designTokens.dark[800], // #1e293b - 卡片底色
    colorBgContainerDisabled: designTokens.dark[700], // #334155

    // 边框/分割线
    colorBorder: designTokens.dark[600], // #475569
    colorBorderSecondary: designTokens.dark[700], // #334155

    // 文字色
    textColorPrimary: designTokens.gray[100], // #f3f4f6 - 主文字
    textColorRegular: designTokens.gray[300], // #d1d5db - 常规文字
    textColorSecondary: designTokens.dark[400], // #94a3b8 - 辅助文字
    textColorDisabled: designTokens.dark[500], // #64748b
    textColorPlaceholder: designTokens.dark[400], // #94a3b8

    // 填充色
    fillColor: designTokens.primary[900], // #134e4a，半透明
    fillColorLight: designTokens.dark[700], // #334155
    fillColorLighter: designTokens.dark[800], // #1e293b
    fillColorExtraLight: designTokens.dark[700],
    fillColorDisabled: designTokens.dark[600], // #475569

    // 尺寸
    borderRadius: 12, // 控件圆角
    borderRadiusLarge: 16, // 容器圆角

    // 阴影
    boxShadow: '0 1px 3px 0 rgb(0 0 0 / 0.3), 0 1px 2px -1px rgb(0 0 0 / 0.3)',
    boxShadowDark: '0 20px 25px -5px rgb(0 0 0 / 0.3), 0 8px 10px -6px rgb(0 0 0 / 0.3)',
  },
}

// 导出设计令牌供全局样式使用
export const themeTokens = {
  light: lightTheme.light,
  dark: darkTheme.dark,
  designTokens,
}
