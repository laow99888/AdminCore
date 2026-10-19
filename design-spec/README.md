# Sub2API 设计规范（Design Spec）

> 从开源项目 [Wei-Shaw/sub2api](https://github.com/Wei-Shaw/sub2api) 前端源码中逐文件提取的真实设计规范。
> 所有数值（色值、字号、间距、圆角、阴影、动效时长）均来自源码 `tailwind.config.js`、`src/style.css` 及组件代码，非目测估计。
> 提取时间：2026-09-29，对应仓库 master 最新版。

## ⚠️ AdminCore 项目适配说明（先读这里）

本规范是一套**跨项目的通用视觉规范**（原项目为 Tailwind + 自研组件 + chart.js 架构）。AdminCore 项目**只采用其视觉语言，不采用其技术栈**：

| 维度 | 规范原文（sub2api） | AdminCore 实际实现 |
|---|---|---|
| UI 组件 | 无组件库，Tailwind 原子类自研 | **Element Plus**（见 [CSS 适配](../frontend/src/styles/globals.css)） |
| 图表 | chart.js + vue-chartjs | **Apache ECharts**（见 `components/common/BaseChart.vue`） |
| 图标 | Heroicons v2 Outline | **Lucide**（同为 24px 描边体系，`lucide-vue-next`） |
| 令牌载体 | `tailwind.config.js` + `style.css` | `frontend/src/styles/design-tokens.css`（CSS 变量） |
| 版本基线 | Vue 3.4 / Vite 5 / Pinia 2 | 以 [版本要求.md](../版本要求.md) 为准（Vue 3.5 / Vite 8 / Pinia 3） |

**沿用不变的**：全部色彩数值（Teal/Slate/灰阶 50–950）、明暗双主题机制（`.dark` class）、间距体系（4px 基数）、侧栏 256px/收缩 72px、顶栏 64px、玻璃拟态与渐变按钮等视觉语言。

**数值换算对照**（design-tokens.css 变量 → 规范术语）：
- `--radius-md: 8px` = 卡内小件（rounded-lg）；`--radius-lg: 12px` = 控件标准（rounded-xl）；`--radius-xl: 16px` = 容器标准（rounded-2xl）
- `--font-size-sm: 14px` = 正文/控件默认（text-sm）；`--font-size-base: 16px` = 长文本/大按钮（text-base）

**仅作参考、不适用于本项目的文件**：`10-AntDesign项目适配.md`、`antd-theme.ts`、`antd-patch.css`（AntD 项目用）、`tailwind.config.reference.js`、`tokens.css`（Tailwind/纯 CSS 项目用）、`效果预览-云媒体平台.html`、`组件预览.html`（原项目产物）。

## 这是一套什么设计

现代 SaaS 控制台风格：**青色（Teal）主色 + 石板灰（Slate）辅色、白色圆角卡片、玻璃拟态顶栏、全站明暗双主题**。整体气质清爽、轻量、偏数据密集型后台。

## 目录

| 文件 | 内容 |
|---|---|
| [01-设计系统概览.md](01-设计系统概览.md) | 技术栈、设计语言、主题机制、源码结构地图 |
| [02-色彩系统.md](02-色彩系统.md) | 全部色板（primary/accent/dark）、语义色映射、暗色镜像规则、图表配色 |
| [03-字体与排版.md](03-字体与排版.md) | 字体族、字号阶梯、标题层级、字重、行高、各场景排版规格 |
| [04-间距圆角阴影.md](04-间距圆角阴影.md) | 间距体系、圆角使用规律、阴影层级、边框、玻璃/模糊效果 |
| [05-布局系统.md](05-布局系统.md) | 应用框架、侧边栏、顶栏、页面骨架、响应式断点、z-index 层级表 |
| [06-组件规范.md](06-组件规范.md) | 按钮/输入框/卡片/表格/徽章/弹窗/Toast/标签页/开关/进度条等全部组件规格 |
| [07-动效规范.md](07-动效规范.md) | 关键帧动画、时长与缓动约定、交互动效、无障碍降级 |
| [08-图标与图表.md](08-图标与图表.md) | Heroicons 图标体系、尺寸档位、图表配色与 chart.js 配置约定 |
| [09-页面构建模板.md](09-页面构建模板.md) | 表格页/仪表盘/登录页/表单弹窗的成品模板 + 一致性检查清单 |
| [10-AntDesign项目适配.md](10-AntDesign项目适配.md) | antd v5/v4 主题映射表与接入步骤（Ant 项目从这里开始） |
| [tokens.css](tokens.css) | 可直接引入的 CSS 变量 + 纯 CSS 组件类（不依赖 Tailwind 也能用） |
| [antd-theme.ts](antd-theme.ts) | Ant Design v5 ConfigProvider 主题（明/暗两套，可直接 import） |
| [antd-patch.css](antd-patch.css) | antd 补丁样式：渐变按钮/玻璃顶栏/氛围背景/徽章四件套 |
| [tailwind.config.reference.js](tailwind.config.reference.js) | 原样可复用的 Tailwind 配置（还原度最高的用法） |

## 如何用这套规范做出高度一致的页面

按投入程度有三档用法，**推荐 B 或 C**：

### A. 只读文档，手写样式
按 02–08 章的数值写 CSS。可行，但容易漏掉暗色模式镜像，一致性风险最高。

### B. 复用 tokens.css（推荐给非 Tailwind 项目）
```html
<link rel="stylesheet" href="tokens.css">
```
所有颜色/间距/圆角/阴影已转成 CSS 变量，按钮、输入框、卡片、表格、弹窗等组件类已写成纯 CSS。写页面时只用这些类，风格自动一致。

### C. 复用 tailwind.config.reference.js（推荐给 Tailwind 项目，还原度 100%）
把参考配置并入你的 `tailwind.config.js`，再把原项目 `style.css` 中的 `@layer components` 段落（见 06 章）拷入你的全局 CSS。之后你写的类名和 sub2api 源码完全同源：`card`、`btn btn-primary`、`input`、`badge badge-success`……

### D. Ant Design 项目走第 10 章
antd 项目不能用上述类名，需要把 token 映射进 antd 主题系统：直接 import `antd-theme.ts`（v5 两套 ThemeConfig）+ 引入 `antd-patch.css`，步骤和映射对照表见 [10-AntDesign项目适配.md](10-AntDesign项目适配.md)。

### 无论哪档，都必须遵守的四条铁律
1. **每个颜色类都写 dark 镜像**：`bg-white dark:bg-dark-800`、`text-gray-900 dark:text-gray-100`，一个都不能少。暗色底统一用 `dark-800`，页面底用 `dark-950`。
2. **语义色用四件套公式**：`bg-{hue}-100 text-{hue}-700 dark:bg-{hue}-900/30 dark:text-{hue}-300`（详见 02 章）。
3. **新页面用现成骨架**：表格页用 09 章「表格页模板」，数据页用「仪表盘模板」，不要自创布局。
4. **过渡时长只用三档**：200ms（hover 等微交互）、250ms（弹层进入）、300ms（卡片/页面入场），缓动统一 `ease-out`。

## 边界说明

- 本规范提取的是**样式事实**（设计 token、组件规格），sub2api 前端代码本身为 MIT 许可（以仓库 LICENSE 为准）；复用时请自行确认许可与品牌元素（其 Logo、站点文案）不直接照搬。
- 项目未使用自定义字体文件，全部系统字体，因此不存在字体授权问题。
