# 10 Ant Design 项目适配指南

> sub2api 的规范是 Tailwind 类名体系，**Ant 项目不能直接引用类名**，正确姿势是把 token 映射进 antd 的主题系统。本目录已提供两个现成文件：
>
> - `antd-theme.ts` —— Ant Design **v5** 的 ConfigProvider 主题（明/暗两套 ThemeConfig）
> - `antd-patch.css` —— token 覆盖不了的少量补丁（渐变按钮、玻璃顶栏、氛围背景、徽章四件套、卡片悬浮）
>
> 映射依据见 02/03/04/06 章；所有色值/圆角/高度均来自原项目。

## 1. v5 接入（三步）

```tsx
import { ConfigProvider, Layout } from 'antd'
import { sub2apiLightTheme, sub2apiDarkTheme } from './antd-theme'
import './antd-patch.css'

// ① 包裹应用
<ConfigProvider theme={isDark ? sub2apiDarkTheme : sub2apiLightTheme}>
  <App />
</ConfigProvider>

// ② 顶栏加玻璃效果
<Layout.Header className="sub2api-glass">…</Layout.Header>

// ③ 主按钮加渐变
<Button type="primary" className="sub2api-gradient">保存</Button>
```

暗色切换机制照抄原项目：`<html>` 上切 `.dark` 类 + `localStorage('theme')` + 首次访问跟随 `prefers-color-scheme`（代码见 01 章）。

## 2. 关键映射对照表

| Sub2API 规范 | antd v5 token | 值 |
|---|---|---|
| primary-500 品牌色 | `colorPrimary` / `colorInfo` | `#14b8a6` |
| emerald/amber/red 语义色 | `colorSuccess` / `colorWarning` / `colorError` | `#10b981` / `#f59e0b` / `#ef4444` |
| gray-50 页面底 | `colorBgLayout` | light `#f9fafb` / dark `#020617` |
| white·dark-800 卡片底 | `colorBgContainer` | light `#ffffff` / dark `#1e293b` |
| gray-200·dark-600 控件边框 | `colorBorder` | light `#e5e7eb` / dark `#475569` |
| 控件圆角 rounded-xl | `borderRadius` | `12` |
| 容器圆角 rounded-2xl | `borderRadiusLG` | `16` |
| 按钮高度（py-2.5 推算） | `controlHeight` | `40` |
| 顶栏高度 | `Layout.headerHeight` | `64` |
| 侧栏激活项 | `Menu.itemSelectedBg` | light `#f0fdfa` / dark `rgba(19,78,74,0.2)` |
| 表头底色 | `Table.headerBg` | light `#f9fafb` / dark `rgba(30,41,59,0.5)` |
| 卡片阴影 shadow-card | `boxShadow` | `0 1px 3px …`（见 ts 文件） |
| 暗色派生 | `theme.darkAlgorithm` | 全局兜底，再显式覆写上表各项 |

## 3. token 覆盖不了、走补丁 CSS 的部分

| 原规范 | 原因 | 补丁类 |
|---|---|---|
| 渐变主按钮 + 按下缩放 | antd Button 无渐变 token | `.sub2api-gradient` |
| 玻璃顶栏（80% 底 + blur 24px） | headerBg 只有底色 | `.sub2api-glass` |
| 页面 mesh 氛围背景 | 无对应 token | `.sub2api-mesh-bg` |
| 徽章四件套暗色公式 | antd Tag 预设色与规范不一致 | `.sub2api-tag-*` |
| 卡片 hover 上浮 2px | antd Card 无 hover token | `.sub2api-card-hover` |

## 4. 间距与布局约定（token 之外靠约定执行）

- 页面区块间距 `24px`（原 space-y-6）；统计卡栅格 `gap 16px`，移动 2 列 / lg 4 列 → `<Row gutter={[16,16]}>` + `xs:12 lg:6`。
- 侧栏宽 256px、收缩 72px → `<Layout.Sider width={256} collapsedWidth={72}>`。
- 内容边距 16/24/32px（响应式）→ 自定义容器 `padding: 16px` + `@media (min-width:768px) 24px` + `(min-width:1024px) 32px`。
- 圆角口诀不变：控件 12、容器 16、药丸 999。
- 动效三档不变：200/250/300ms + ease-out。

## 5. Ant Design v4 项目

v4 用 Less 变量，映射子集（其余靠 antd-patch.css，类名相同）：

```js
// craco/vite less modifyVars
{
  '@primary-color': '#14b8a6',
  '@success-color': '#10b981',
  '@warning-color': '#f59e0b',
  '@error-color': '#ef4444',
  '@text-color': '#374151',
  '@text-color-secondary': '#6b7280',
  '@border-color-base': '#e5e7eb',
  '@border-color-split': '#f3f4f6',
  '@background-color-light': '#f9fafb',
  '@layout-body-background': '#f9fafb',
  '@layout-header-background': 'rgba(255,255,255,0.8)',
  '@border-radius-base': '12px',
  '@border-radius-lg': '16px',
  '@btn-border-radius-base': '12px',
  '@font-family': "system-ui, -apple-system, 'Segoe UI', Roboto, 'PingFang SC', 'Microsoft YaHei', sans-serif",
  '@table-header-bg': '#f9fafb',
  '@table-row-hover-bg': '#f9fafb',
}
```

v4 暗色没有 darkAlgorithm，需要社区暗色变量包（如 `antd-dark-theme`）或按 02 章对照表手工覆写 Less 变量——工作量明显大于 v5，建议优先 v5。

## 6. 适配后的验收清单

- [ ] `colorPrimary` 换成 `#14b8a6` 后，Button/Switch/Progress/Checkbox/Pagination 的选中态全部变青
- [ ] 暗色下页面底 `#020617`、卡片 `#1e293b`、边框 `#475569`，无纯白残留
- [ ] 主按钮有渐变 + 按下 `scale(0.98)`（补丁类生效）
- [ ] Table 行 hover 与表头底色与规范一致
- [ ] 侧栏激活项底色 `#f0fdfa`（light）
- [ ] 弹窗圆角 16px、圆角无 6px 残留（antd 默认值必须被 token 覆盖）
