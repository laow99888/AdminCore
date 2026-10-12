import { ref } from 'vue'

// 侧栏折叠状态（模块级单例，AppSidebar 与 AppHeader 共享）
// 桌面端：collapsed = 72px 图标栏；移动端（≤768px）：collapsed = 抽屉关闭
const isCollapsed = ref(false)
const isMobile = ref(false)

if (typeof window !== 'undefined' && window.matchMedia) {
  const mq = window.matchMedia('(max-width: 768px)')
  const sync = () => {
    isMobile.value = mq.matches
    // 初始及每次进入移动端时，抽屉默认关闭
    if (mq.matches) isCollapsed.value = true
  }
  sync()
  mq.addEventListener('change', sync)
}

export function useSidebar() {
  const toggle = () => {
    isCollapsed.value = !isCollapsed.value
  }
  const open = () => {
    isCollapsed.value = false
  }
  const close = () => {
    isCollapsed.value = true
  }
  return { isCollapsed, isMobile, toggle, open, close }
}
