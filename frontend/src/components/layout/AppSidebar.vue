<template>
  <!-- 移动端抽屉遮罩 -->
  <div
    v-if="isMobile && !isCollapsed"
    class="sidebar-backdrop"
    aria-hidden="true"
    @click="close"
  ></div>

  <aside class="app-sidebar" :class="{ collapsed: isCollapsed }">
    <!-- Logo 区域 -->
    <div class="sidebar-logo">
      <div class="logo-icon">
        <span v-if="!isCollapsed">AdminCore</span>
        <span v-else>AC</span>
      </div>
    </div>

    <!-- 菜单导航 -->
    <nav class="sidebar-menu">
      <router-link
        v-for="item in menuItems"
        :key="item.path"
        :to="item.path"
        class="menu-item"
        :class="{ active: isActive(item.path) }"
        @click="onNavigate"
      >
        <span class="menu-icon">
          <component :is="item.icon" :size="18" :stroke-width="1.75" />
        </span>
        <span v-if="!isCollapsed" class="menu-label">{{ item.label }}</span>
        <el-tooltip v-else :content="item.label" placement="right">
          <span></span>
        </el-tooltip>
      </router-link>
    </nav>

    <!-- 侧栏底部 -->
    <div class="sidebar-footer">
      <button
        class="collapse-btn"
        :title="isCollapsed ? uiText('展开') : uiText('收起')"
        :aria-label="isCollapsed ? uiText('展开侧栏') : uiText('收起侧栏')"
        @click="toggleCollapse"
      >
        <component :is="isCollapsed ? ChevronsRight : ChevronsLeft" :size="16" :stroke-width="1.75" />
      </button>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { uiText } from "@/i18n/uiText"

import { ref, computed, onMounted } from 'vue'
import { menusApi } from '../../api'
import { useAuthStore } from '../../stores/auth'
import type { Component } from 'vue'
import { useRoute } from 'vue-router'
import { useSidebar } from '../../composables/useSidebar'
import {
  LayoutDashboard, Users, ShieldCheck, ListTree, FolderOpen,
  ListChecks, ClipboardCheck, FileText, Bell, Settings,
  ChevronsLeft, ChevronsRight,
} from 'lucide-vue-next'

const route = useRoute()
const { isCollapsed, isMobile, toggle: toggleCollapse, close } = useSidebar()

// 移动端点击菜单后自动收起抽屉
const onNavigate = () => {
  if (isMobile.value) close()
}

interface MenuItem {
  path: string
  label: string
  icon: Component
}

// 菜单项（Lucide 线性图标，24px 网格）
const configuredMenuItems: MenuItem[] = [
  { path: '/', label: uiText("仪表盘"), icon: LayoutDashboard },
  { path: '/users', label: uiText("用户管理"), icon: Users },
  { path: '/roles', label: uiText("角色权限"), icon: ShieldCheck },
  { path: '/menus', label: uiText("菜单管理"), icon: ListTree },
  { path: '/files', label: uiText("文件管理"), icon: FolderOpen },
  { path: '/tasks', label: uiText("任务中心"), icon: ListChecks },
  { path: '/approvals', label: uiText("审批工作流"), icon: ClipboardCheck },
  { path: '/logs', label: uiText("操作日志"), icon: FileText },
  { path: '/notifications', label: uiText("通知中心"), icon: Bell },
  { path: '/settings', label: uiText("系统设置"), icon: Settings },
]
const auth = useAuthStore()
const allowedPaths = ref<string[]>([])
const menuItems = computed(() => configuredMenuItems.filter((item) => allowedPaths.value.includes(item.path)))
onMounted(async () => {
  if (!auth.user?.permissions) await auth.fetchUser()
  try {
    const flatten = (items: Awaited<ReturnType<typeof menusApi.myMenu>>): string[] =>
      items.flatMap((item) => [item.path, ...flatten(item.children || [])])
    allowedPaths.value = flatten(await menusApi.myMenu())
  } catch {
    allowedPaths.value = ['/', '/settings']
  }
})

// 判断当前菜单项是否为活跃
const isActive = (path: string) => {
  return route.path === path || route.path.startsWith(path + '/')
}

</script>

<style scoped>
.app-sidebar {
  width: var(--sidebar-width);
  height: 100vh;
  background-color: var(--color-bg-card);
  border-right: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  transition:
    width var(--transition-normal),
    transform var(--transition-normal);
  overflow: hidden;
}

.app-sidebar.collapsed {
  width: var(--sidebar-collapsed-width);
}

/* 移动端抽屉遮罩 */
.sidebar-backdrop {
  position: fixed;
  inset: 0;
  background: rgb(15 23 42 / 0.5);
  z-index: 1000;
}

/* Logo 区域 */
.sidebar-logo {
  height: var(--header-height);
  display: flex;
  align-items: center;
  justify-content: center;
  border-bottom: 1px solid var(--color-border);
  padding: 0 var(--spacing-md);
  min-height: var(--header-height);
}

.logo-icon {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
  background: linear-gradient(135deg, #14b8a6 0%, #0d9488 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  white-space: nowrap;
  user-select: none;
}

/* 菜单导航 */
.sidebar-menu {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-md) 0;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.menu-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-md);
  margin: 0 var(--spacing-sm);
  border-radius: var(--radius-lg);
  color: var(--color-text-secondary);
  text-decoration: none;
  transition: all var(--transition-fast);
  cursor: pointer;
  font-size: var(--font-size-sm);
}

.menu-item:hover {
  color: var(--color-primary-500);
  background-color: var(--color-bg-elevated);
}

.menu-item.active {
  color: var(--color-primary-500);
  background-color: rgb(20 184 166 / 0.1);
  font-weight: var(--font-weight-semibold);
}

.menu-icon {
  font-size: var(--font-size-lg);
  flex-shrink: 0;
  width: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.menu-label {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 侧栏底部 */
.sidebar-footer {
  border-top: 1px solid var(--color-border);
  padding: var(--spacing-md);
  display: flex;
  justify-content: center;
}

.collapse-btn {
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
}

.collapse-btn:hover {
  background-color: var(--color-primary-100);
  color: var(--color-primary-500);
}

/* 滚动条 */
.sidebar-menu::-webkit-scrollbar {
  width: 4px;
}

.sidebar-menu::-webkit-scrollbar-thumb {
  background: var(--color-border);
  border-radius: 2px;
}

.sidebar-menu::-webkit-scrollbar-thumb:hover {
  background: var(--color-primary-500);
}

/* 响应式：移动端为抽屉（默认移出屏幕，展开时覆盖内容） */
@media (max-width: 768px) {
  .app-sidebar {
    position: fixed;
    left: 0;
    top: 0;
    z-index: 1001;
    height: 100vh;
    width: var(--sidebar-width);
    box-shadow: var(--shadow-xl);
  }

  .app-sidebar.collapsed {
    width: var(--sidebar-width);
    transform: translateX(-100%);
    box-shadow: none;
  }
}
</style>
