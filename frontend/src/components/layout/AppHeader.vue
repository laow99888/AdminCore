<template>
  <header class="app-header">
    <div class="header-left">
      <button
        class="action-btn mobile-menu-btn"
        :aria-label="isCollapsed ? uiText('打开菜单') : uiText('关闭菜单')"
        @click="toggleSidebar"
      >
        <Menu :size="18" :stroke-width="1.75" />
      </button>
      <component :is="route.meta.hasPageHeading ? 'span' : 'h1'" class="header-title">{{ currentPageTitle }}</component>
    </div>

    <div class="header-right">
      <!-- 搜索框 -->
      <div class="search-box">
        <el-input
          v-model="searchQuery"
          :placeholder="uiText('搜索...')"
          clearable
          class="search-input"
        >
          <template #prefix>
            <Search :size="15" :stroke-width="1.75" class="search-icon" />
          </template>
        </el-input>
      </div>

      <!-- 通知 -->
      <div v-if="modules.enabled('notifications')" class="header-action">
        <el-badge :value="notificationCount" :hidden="notificationCount === 0" class="notification-badge">
          <button class="action-btn" :title="uiText('通知中心')" :aria-label="uiText('通知中心')" @click="router.push('/notifications')">
            <Bell :size="17" :stroke-width="1.75" />
          </button>
        </el-badge>
      </div>

      <!-- 主题切换 -->
      <div class="header-action">
        <button
          class="action-btn"
          :title="isDark ? uiText('浅色模式') : uiText('深色模式')"
          :aria-label="isDark ? uiText('切换到浅色模式') : uiText('切换到深色模式')"
          @click="toggleTheme"
        >
          <Sun v-if="isDark" :size="17" :stroke-width="1.75" />
          <Moon v-else :size="17" :stroke-width="1.75" />
        </button>
      </div>

      <!-- 快捷键帮助 -->
      <div class="header-action">
        <button class="action-btn shortcut-help" :title="uiText('快捷键帮助')" :aria-label="uiText('快捷键帮助')" @click="openKeyboardHelp">
          <Keyboard :size="17" :stroke-width="1.75" aria-hidden="true" />
        </button>
      </div>

      <!-- 语言切换 -->
      <div class="header-action">
        <el-dropdown @command="switchLanguage">
          <button class="action-btn" :title="uiText('切换语言')" :aria-label="uiText('切换语言')">
            <Languages :size="17" :stroke-width="1.75" />
          </button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="zh-CN">{{ uiText("中文") }}</el-dropdown-item>
              <el-dropdown-item command="en-US">English</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>

      <!-- 用户菜单 -->
      <div class="header-action">
        <el-dropdown @command="handleCommand">
          <button class="action-btn user-btn" :aria-label="uiText('用户菜单')">
            <span class="user-avatar">
              <PrivateAvatar :icon-size="15" />
            </span>
            <span class="user-name">{{ displayName }}</span>
          </button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="profile">{{ uiText("个人中心") }}</el-dropdown-item>
              <el-dropdown-item command="settings">{{ uiText("账户设置") }}</el-dropdown-item>
              <el-dropdown-item command="logout" divided>{{ uiText("退出登录") }}</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { uiText } from "@/i18n/uiText"

import { onMounted, onUnmounted, onActivated, onDeactivated, watch, ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useThemeStore } from '../../stores/theme'
import { useAuthStore } from '../../stores/auth'
import { notificationsApi } from '../../api'
import { useI18n } from 'vue-i18n'
import { Search, Bell, Sun, Moon, Languages, Menu, Keyboard } from 'lucide-vue-next'
import { KEYBOARD_HELP_EVENT } from '@/utils/keyboardShortcuts'
import { confirmPendingForms } from '@/composables/useUnsavedChanges'
import PrivateAvatar from '@/components/auth/PrivateAvatar.vue'
import { useSidebar } from '../../composables/useSidebar'
import { useModuleStore } from '@/stores/modules'
import { REALTIME_EVENT, startRealtimeClient } from '@/utils/realtime'

const route = useRoute()
const router = useRouter()
const themeStore = useThemeStore()
const authStore = useAuthStore()
const modules = useModuleStore()
const { locale } = useI18n()
const { isCollapsed, toggle: toggleSidebar } = useSidebar()

const searchQuery = ref('')
function openKeyboardHelp() { window.dispatchEvent(new Event(KEYBOARD_HELP_EVENT)) }
const notificationCount = ref(0)

const isDark = computed(() => themeStore.isDark)
const displayName = computed(() => authStore.user?.username || 'Admin')

// 未读通知数轮询
let pollTimer: number | undefined
let active = true
let unreadGeneration = 0
let stopRealtime: (() => void) | undefined
const refreshUnread = async () => {
  if (!active || !authStore.user || !modules.enabled('notifications')) return
  const generation = ++unreadGeneration
  const owner = authStore.user.id
  try {
    const count = await notificationsApi.unreadCount()
    if (active && generation === unreadGeneration && owner === authStore.user?.id && modules.enabled('notifications')) notificationCount.value = count
  } catch {
    // 静默失败，下一轮再试
  }
}
function startPolling() {
  window.clearInterval(pollTimer)
  stopRealtime?.(); stopRealtime = undefined
  unreadGeneration++
  notificationCount.value = 0
  if (active && modules.enabled('notifications')) {
    refreshUnread()
    pollTimer = window.setInterval(refreshUnread, 60000)
  }
  if (active && authStore.user && !authStore.user.must_change_password && modules.enabled('realtime')) {
    stopRealtime = startRealtimeClient({ enabled: () => active && modules.enabled('realtime') && !!authStore.user && !authStore.user.must_change_password,
      onAuthExpired: () => authStore.fetchUser(true),
      onSnapshot: topics => {
        unreadGeneration++
        notificationCount.value = topics.notifications?.unread_count ?? 0
        window.dispatchEvent(new CustomEvent(REALTIME_EVENT, { detail: topics }))
      } })
  }
}
onMounted(startPolling)
onActivated(() => { active = true; startPolling() })
onDeactivated(() => { active = false; unreadGeneration++; window.clearInterval(pollTimer); stopRealtime?.() })
watch([() => modules.enabled('notifications'), () => modules.enabled('realtime'), () => authStore.user?.id, () => authStore.token,
  () => authStore.user?.must_change_password, () => JSON.stringify(authStore.user?.permissions)], startPolling)
onUnmounted(() => { active = false; unreadGeneration++; window.clearInterval(pollTimer); stopRealtime?.() })

// 当前页面标题
const currentPageTitle = computed(() => {
  return typeof route.meta.title === 'string' ? uiText(route.meta.title) : 'AdminCore'
})

// 切换主题
const toggleTheme = () => {
  themeStore.toggleTheme()
}

// 切换语言
const switchLanguage = async (command: string) => {
  if (command === locale.value || !['zh-CN', 'en-US'].includes(command)) return
  if (!route.meta.preserveOnLocaleChange && !await confirmPendingForms()) return
  locale.value = command
  localStorage.setItem('language', command)
}

// 用户菜单命令
const handleCommand = async (command: string) => {
  switch (command) {
    case 'profile':
      router.push('/settings')
      break
    case 'settings':
      router.push('/settings')
      break
    case 'logout':
      await authStore.logout()
      router.push('/login')
      break
  }
}
</script>

<style scoped>
.app-header {
  height: var(--header-height);
  background-color: var(--color-bg-card);
  border-bottom: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--spacing-xl);
  gap: var(--spacing-lg);
  flex-shrink: 0;
  backdrop-filter: blur(10px);
  background-color: rgba(255, 255, 255, 0.8);
  z-index: 100;
}

.dark .app-header {
  background-color: rgba(30, 41, 59, 0.8);
}

.header-left {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

/* 移动端菜单按钮：桌面隐藏 */
.mobile-menu-btn {
  display: none;
  flex-shrink: 0;
}

.header-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-right {
  display: flex;
  align-items: center;
  gap: var(--spacing-lg);
  flex-shrink: 0;
}

/* 搜索框 */
.search-box {
  width: 200px;
}

.search-input {
  --el-input-height: 36px;
}

:deep(.search-input .el-input__wrapper) {
  background-color: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
}

/* 操作按钮组 */
.header-action {
  position: relative;
}

.action-btn {
  width: 36px;
  height: 36px;
  border: none;
  border-radius: var(--radius-lg);
  background-color: var(--color-bg-elevated);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-sm);
  padding: 0;
}

.action-btn:hover {
  background-color: var(--admincore-primary-subtle, var(--color-primary-100));
  color: var(--color-primary-500);
}

.user-btn {
  width: auto;
  gap: var(--spacing-sm);
  padding: 0 var(--spacing-md);
}

.shortcut-help { width: 44px; height: 44px; }

.user-avatar {
  font-size: var(--font-size-sm);
}

.user-name {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  max-width: 80px;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 通知徽章 */
.notification-badge {
  display: flex;
}

/* 响应式 */
@media (max-width: 1024px) {
  .search-box {
    display: none;
  }
}

@media (max-width: 768px) {
  .header-right { gap: var(--spacing-xs); }
  .app-header {
    padding: 0 var(--spacing-lg);
    gap: var(--spacing-md);
  }

  .mobile-menu-btn {
    display: flex;
  }

  .user-name {
    display: none;
  }
}
</style>
