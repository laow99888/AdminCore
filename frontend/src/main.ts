import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import { i18n } from './i18n'
import { useBrandStore } from './stores/brand'
import { useThemeStore } from './stores/theme'
import { errorReporter, installErrorReporting } from './utils/errorReporting'
import { loadFullUiMessages } from './i18n/uiText'
import { initializeBrowserSession, startBrowserSessionSync } from './auth/browserSession'

// Element Plus 基础样式与暗色变量（必须先于全局覆盖引入）
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'

// 设计令牌和全局样式（含 Element Plus 主题映射，需在 EP 样式之后）
import './styles/design-tokens.css'
import './styles/globals.css'

const app = createApp(App)

// 完整文案异步加载；首屏核心文案仍由 uiMessages.ts 提供。
void loadFullUiMessages()

// Element Plus 组件及指令由构建插件按需导入，语言由 App 的配置提供器控制。

// 注册 Pinia
app.use(createPinia())
useThemeStore()
useBrandStore().load()

// 注册路由
errorReporter.registerRoutes(router.getRoutes().map(route => route.path))
let recoveringNavigation = false
const disposeErrorReporting = installErrorReporting({
  app, router,
  onVueError: () => window.dispatchEvent(new Event('admincore:vue-error')),
  onNavigationError: () => {
    if (recoveringNavigation || router.currentRoute.value.path === '/500') return
    recoveringNavigation = true
    void router.replace('/500').catch(() => {}).finally(() => { recoveringNavigation = false })
  },
})
app.onUnmount(disposeErrorReporting)
if (import.meta.hot) import.meta.hot.dispose(disposeErrorReporting)
// 注册 i18n
app.use(i18n)

const disposeSessionSync = startBrowserSessionSync(() => window.location.replace('/login'))
app.onUnmount(disposeSessionSync)
if (import.meta.hot) import.meta.hot.dispose(disposeSessionSync)
// Cookie 模式先完成内存会话恢复，再让路由检查登录态；旧模式不发起额外请求。
void initializeBrowserSession().then(() => true, () => false).then(ready => {
  app.use(router)
  if (!ready) void router.isReady().then(() => router.replace('/unavailable'))
  app.mount('#app')
})
