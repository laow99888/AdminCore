<template>
  <el-dialog v-model="opened" :title="uiText('快捷键帮助')" width="min(560px, calc(100vw - 32px))" class="keyboard-shortcuts-dialog" :close-on-click-modal="false">
    <div class="shortcut-preference">
      <div>
        <strong id="shortcut-description">{{ uiText('键盘快捷键') }}</strong>
        <p>{{ uiText('默认关闭，仅保存在本浏览器；关闭后仍可使用鼠标导航。') }}</p>
      </div>
      <el-switch :model-value="enabled" :aria-label="uiText('启用键盘快捷键')" aria-describedby="shortcut-description" @change="setEnabled" />
    </div>
    <p v-if="!persistenceAvailable" role="status" class="shortcut-warning">{{ uiText('浏览器无法保存快捷键偏好，当前设置仅在本次页面会话内生效。') }}</p>
    <dl class="shortcut-list">
      <div v-for="command in keyboardCommands" :key="command.key">
        <dt>{{ uiText(command.title) }}</dt><dd><kbd>{{ command.key }}</kbd></dd>
      </div>
    </dl>
    <p class="shortcut-note">{{ uiText('输入文字、组合输入或弹窗打开时不触发；只访问有权限的页面，关闭页签仍会检查未保存的修改。') }}</p>
    <template #footer><el-button @click="opened = false">{{ uiText('关闭') }}</el-button></template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onActivated, onDeactivated, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useModuleStore } from '@/stores/modules'
import { useNavigationStore } from '@/stores/navigation'
import { canAccessPage } from '@/router/access'
import { uiText } from '@/i18n/uiText'
import { keyboardCommands, installKeyboardShortcuts, readKeyboardPreference, writeKeyboardPreference } from '@/utils/keyboardShortcuts'

const router = useRouter(), auth = useAuthStore(), modules = useModuleStore(), navigation = useNavigationStore()
// This component belongs at the application root, outside route KeepAlive.
const preference = readKeyboardPreference(localStorage)
const enabled = ref(preference.enabled), persistenceAvailable = ref(preference.persistenceAvailable), opened = ref(false)
const active = computed(() => auth.isAuthenticated && !!auth.user && !auth.user.must_change_password &&
  router.currentRoute.value.meta.requiresAuth === true && router.currentRoute.value.path !== '/change-password' &&
  canAccessPage(router.currentRoute.value.path, auth.user, modules.pagePermissions) && modules.pathEnabled(router.currentRoute.value.path))
function allowed(path: string) {
  const resolved = router.resolve(path)
  return resolved.matched.length > 0 && resolved.meta.requiresAuth === true && path !== '/change-password' &&
    canAccessPage(path, auth.user, modules.pagePermissions) && modules.pathEnabled(path)
}
function setEnabled(value: string | number | boolean) {
  enabled.value = value === true
  persistenceAvailable.value = writeKeyboardPreference(localStorage, enabled.value)
}
function openHelp() { if (active.value) opened.value = true }
let stop: (() => void) | undefined
function start() {
  if (stop) return
  stop = installKeyboardShortcuts(window, () => ({
    enabled: enabled.value, active: active.value, path: router.currentRoute.value.path, tabs: navigation.tabs,
    allowed, navigate: path => router.push(path), close: path => navigation.close(path, router), help: openHelp,
  }), openHelp)
}
function suspend() { stop?.(); stop = undefined; opened.value = false }
watch([active, () => auth.user?.id], () => { opened.value = false })
onMounted(start)
onActivated(start)
onDeactivated(suspend)
onBeforeUnmount(suspend)
</script>

<style scoped>
.shortcut-preference { display: flex; align-items: center; justify-content: space-between; gap: var(--spacing-md); }
.shortcut-preference strong { color: var(--color-text-primary); }
.shortcut-preference p, .shortcut-note { margin: var(--spacing-xs) 0; color: var(--color-text-secondary); line-height: 1.6; overflow-wrap: anywhere; }
.shortcut-preference :deep(.el-switch) { flex-shrink: 0; min-width: 44px; min-height: 44px; }
.shortcut-warning { color: var(--color-warning); line-height: 1.6; }
.shortcut-list { margin: var(--spacing-lg) 0; }
.shortcut-list > div { display: flex; justify-content: space-between; align-items: center; gap: var(--spacing-md); padding: var(--spacing-sm) 0; border-bottom: 1px solid var(--color-border); }
.shortcut-list dt { color: var(--color-text-primary); }
.shortcut-list dd { margin: 0; flex-shrink: 0; }
kbd { border: 1px solid var(--color-border); border-radius: var(--radius-sm); padding: 4px 6px; color: var(--color-text-primary); background: var(--color-bg-elevated); font-size: var(--font-size-sm); white-space: nowrap; }
:deep(.el-button) { min-height: 44px; }
</style>
