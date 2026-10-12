import { theme } from 'antd'
import type { ThemeConfig } from 'antd'

/**
 * Sub2API 设计规范 → Ant Design v5 主题映射
 * 提取自 https://github.com/Wei-Shaw/sub2api（详见同目录 02/03/04/06 章）
 *
 * 用法：
 *   import { ConfigProvider } from 'antd'
 *   import { sub2apiLightTheme, sub2apiDarkTheme } from './antd-theme'
 *
 *   <ConfigProvider theme={isDark ? sub2apiDarkTheme : sub2apiLightTheme}>
 *     <App />
 *   </ConfigProvider>
 *
 * 暗色切换仍按原规范：在 <html> 上切 .dark 类 + localStorage('theme') 持久化
 * （antd 的 darkAlgorithm 负责组件派生色，页面底色/文字仍建议用 10 章的变量）。
 */

const FONT_SANS =
  "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif"

/* ---------- 共享形状/字体 token（明暗一致） ---------- */
const shape = {
  fontSize: 14,               // 全站默认字号 text-sm
  fontFamily: FONT_SANS,
  controlHeight: 40,          // 原 .btn/.input：py-2.5 + 20px 行高 ≈ 40px
  borderRadius: 12,           // 控件圆角 rounded-xl
  borderRadiusSM: 8,          // rounded-lg
  borderRadiusLG: 16,         // 容器圆角 rounded-2xl
  // 动效三档（07 章：150ms 行 hover / 200ms 微交互 / 300ms 卡片与入场）
  motionDurationFast: '0.15s',
  motionDurationMid: '0.2s',
  motionDurationSlow: '0.3s',
  wireframe: false,
}

/* ---------- Light 主题 ---------- */
export const sub2apiLightTheme: ThemeConfig = {
  token: {
    ...shape,
    // 语义色（02 章）
    colorPrimary: '#14b8a6',   // primary-500
    colorInfo: '#14b8a6',
    colorSuccess: '#10b981',   // emerald-500
    colorWarning: '#f59e0b',   // amber-500
    colorError: '#ef4444',     // red-500
    colorLink: '#0d9488',      // primary-600
    // 中性（light：gray 系）
    colorTextBase: '#111827',  // gray-900
    colorBgLayout: '#f9fafb',  // gray-50 页面底
    colorBgContainer: '#ffffff',
    colorBgElevated: '#ffffff',
    colorBorder: '#e5e7eb',    // gray-200 控件边框
    colorBorderSecondary: '#f3f4f6', // gray-100 卡片边框
    // 阴影（04 章）
    boxShadow: '0 1px 3px rgba(0, 0, 0, 0.04), 0 1px 2px rgba(0, 0, 0, 0.06)', // shadow-card
    boxShadowSecondary: '0 8px 32px rgba(0, 0, 0, 0.08)',                       // shadow-glass
  },
  components: {
    Layout: {
      headerHeight: 64,          // 顶栏 h-16
      headerBg: 'rgba(255, 255, 255, 0.8)', // glass 底，配合 antd-patch.css 的模糊
      bodyBg: '#f9fafb',
      siderBg: '#ffffff',        // 侧栏白底（暗色 dark-900）
    },
    Menu: {
      itemHeight: 40,            // sidebar-link py-2.5 + 20px 行高
      itemBorderRadius: 12,
      itemColor: '#4b5563',      // gray-600
      itemHoverBg: '#f3f4f6',    // gray-100
      itemSelectedBg: '#f0fdfa', // primary-50
      itemSelectedColor: '#0d9488',
      groupTitleFontSize: 12,    // 分节标题 text-xs
    },
    Button: {
      fontWeight: 500,
      primaryShadow: '0 4px 6px -1px rgba(20, 184, 166, 0.25)', // 同色染阴影
      defaultShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
      // 渐变底需配合 antd-patch.css 的 .sub2api-gradient
    },
    Card: {},
    Table: {
      headerBg: '#f9fafb',
      headerColor: '#4b5563',
      rowHoverBg: '#f9fafb',
      borderColor: '#f3f4f6',          // 行分隔线 gray-100
      headerSplitColor: 'transparent',
    },
    Modal: {},
    Tag: { borderRadiusSM: 999 },      // 徽章药丸形
    Progress: { remainingColor: '#e5e7eb' },
    Segmented: { trackBg: '#f3f4f6', itemSelectedBg: '#ffffff' }, // .tabs 外壳
    Switch: {},                        // 尺寸走 controlHeight 派生
  },
}

/* ---------- Dark 主题 ---------- */
export const sub2apiDarkTheme: ThemeConfig = {
  algorithm: theme.darkAlgorithm,
  token: {
    ...shape,
    colorPrimary: '#14b8a6',
    colorInfo: '#14b8a6',
    colorSuccess: '#10b981',
    colorWarning: '#f59e0b',
    colorError: '#ef4444',
    colorLink: '#2dd4bf',             // primary-400（暗色强调用 400 档）
    // 中性（dark：slate 系，02 章对照表）
    colorTextBase: '#f3f4f6',         // gray-100
    colorBgLayout: '#020617',         // dark-950 页面底
    colorBgContainer: '#1e293b',      // dark-800 卡片底
    colorBgElevated: '#1e293b',       // 弹窗/下拉同卡片
    colorBorder: '#475569',           // dark-600 控件边框
    colorBorderSecondary: 'rgba(51, 65, 85, 0.5)', // dark-700/50 卡片边框
    boxShadow: '0 1px 3px rgba(0, 0, 0, 0.04), 0 1px 2px rgba(0, 0, 0, 0.06)',
    boxShadowSecondary: '0 8px 32px rgba(0, 0, 0, 0.08)',
  },
  components: {
    Layout: {
      headerBg: 'rgba(30, 41, 59, 0.8)',  // dark-800/80 玻璃底
      bodyBg: '#020617',
      siderBg: '#0f172a',                 // dark-900
    },
    Menu: {
      itemColor: '#94a3b8',               // dark-400
      itemHoverBg: '#1e293b',
      itemSelectedBg: 'rgba(19, 78, 74, 0.2)', // primary-900/20
      itemSelectedColor: '#2dd4bf',       // primary-400
    },
    Table: {
      headerBg: 'rgba(30, 41, 59, 0.5)',  // dark-800/50 粘性表头同款
      headerColor: '#cbd5e1',             // dark-300
      rowHoverBg: 'rgba(30, 41, 59, 0.3)',
      borderColor: '#1e293b',             // dark-800
    },
    Progress: { remainingColor: '#334155' },
    Segmented: { trackBg: '#1e293b', itemSelectedBg: '#334155' },
  },
}
