import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import { i18n } from './i18n'

// Element Plus 基础样式与暗色变量（必须先于全局覆盖引入）
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'

// 设计令牌和全局样式（含 Element Plus 主题映射，需在 EP 样式之后）
import './styles/design-tokens.css'
import './styles/globals.css'

const app = createApp(App)

// 获取保存的主题
const savedTheme = localStorage.getItem('theme') || 'light'
const isDark = savedTheme === 'dark'
if (isDark) {
  document.documentElement.classList.add('dark')
}

// 注册 Element Plus
app.use(ElementPlus, {
  locale: zhCn,
})

// 注册 Pinia
app.use(createPinia())

// 注册路由
app.use(router)

// 注册 i18n
app.use(i18n)

app.mount('#app')
