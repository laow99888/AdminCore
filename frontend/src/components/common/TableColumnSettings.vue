<template>
  <el-popover v-model:visible="visible" placement="bottom-end" :width="360" trigger="click" popper-class="table-columns-popover">
    <template #reference><el-button ref="triggerButton" :aria-label="uiText('列设置')"><Columns3 :size="16" aria-hidden="true" />{{ uiText('列设置') }}</el-button></template>
    <div class="column-settings" role="group" :aria-label="uiText('列设置')" @keydown.esc.stop="close">
      <div class="settings-head"><strong>{{ uiText('列设置') }}</strong><el-button link @click="reset">{{ uiText('恢复默认') }}</el-button><el-button link :aria-label="uiText('关闭列设置')" @click="close">{{ uiText('关闭') }}</el-button></div>
      <p v-if="!owner" role="status">{{ uiText('登录后才会保存列设置') }}</p>
      <p v-if="persistenceUnavailable" role="status">{{ uiText('无法保存偏好，本次页面内仍可使用') }}</p>
      <div v-for="(item, index) in layout" :key="item.prop" class="column-setting-row" :data-column-setting="item.prop">
        <el-checkbox :model-value="item.visible" :disabled="item.visible && visibleCount === 1" @change="change(item.prop, { visible: $event === true })">{{ label(item.prop) }}</el-checkbox>
        <div class="column-controls">
          <el-select :model-value="item.fixed || 'none'" :aria-label="label(item.prop) + ' ' + uiText('固定位置')" @update:model-value="change(item.prop, { fixed: $event === 'left' || $event === 'right' ? $event : false })">
            <el-option value="none" :label="uiText('不固定')" /><el-option value="left" :label="uiText('固定左侧')" /><el-option value="right" :label="uiText('固定右侧')" />
          </el-select>
          <el-button :aria-label="label(item.prop) + ' ' + uiText('上移')" :disabled="index === 0" @click="move(index, -1)"><ArrowUp :size="16" aria-hidden="true" /></el-button>
          <el-button :aria-label="label(item.prop) + ' ' + uiText('下移')" :disabled="index === layout.length - 1" @click="move(index, 1)"><ArrowDown :size="16" aria-hidden="true" /></el-button>
        </div>
      </div>
    </div>
  </el-popover>
</template>
<script setup lang="ts">
import { computed, nextTick, ref, toRef, watch } from 'vue'
import type { ButtonInstance } from 'element-plus'
import { ArrowDown, ArrowUp, Columns3 } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth'
import { useTenantStore } from '@/stores/tenants'
import { useColumnPreferences, type ColumnPreference, type ConfigurableColumn } from '@/composables/useColumnPreferences'
import { registerUiMessages, uiText } from '@/i18n/uiText'
registerUiMessages({ '关闭列设置': 'Close column settings' })
registerUiMessages({ '列设置': 'Columns', '固定位置': 'Pin position', '不固定': 'Unpinned', '固定左侧': 'Pin left', '固定右侧': 'Pin right', '上移': 'Move up', '下移': 'Move down', '恢复默认': 'Reset defaults', '登录后才会保存列设置': 'Sign in to save column preferences', '无法保存偏好，本次页面内仍可使用': 'Preferences cannot be saved, but remain available on this page', '字段权限': 'Field permissions' })
const props = defineProps<{ preferenceKey: string; columns: ConfigurableColumn[] }>()
const emit = defineEmits<{ change: [layout: ColumnPreference[]] }>()
const visible = ref(false), triggerButton = ref<ButtonInstance>()
async function close() { visible.value = false; await nextTick(); triggerButton.value?.$el?.focus() }
const auth = useAuthStore(), tenants = useTenantStore()
const owner = computed(() => auth.user?.id ? JSON.stringify([auth.user.id, tenants.currentId || 'global']) : '')
const { layout, persistenceUnavailable, save, reset } = useColumnPreferences(toRef(props, 'preferenceKey'), toRef(props, 'columns'), owner)
const visibleCount = computed(() => layout.value.filter(item => item.visible).length)
const label = (prop: string) => props.columns.find(column => column.prop === prop)?.label ?? prop
watch(layout, value => emit('change', value), { immediate: true, deep: true, flush: 'sync' })
function change(prop: string, value: Partial<ColumnPreference>) { save(layout.value.map(item => item.prop === prop ? { ...item, ...value } : item)) }
function move(index: number, step: number) {
  const next = [...layout.value]
  if (index + step < 0 || index + step >= next.length) return
  ;[next[index], next[index + step]] = [next[index + step]!, next[index]!]
  save(next)
}
</script>
<style scoped>
.column-settings { max-height: min(65vh, 520px); overflow-y: auto; }
:global(.table-columns-popover) { max-width: calc(100vw - 24px); box-sizing: border-box; }
.settings-head, .column-setting-row, .column-controls { display: flex; align-items: center; gap: var(--spacing-sm); }
.settings-head, .column-setting-row { justify-content: space-between; }
.column-setting-row { flex-wrap: wrap; padding-block: var(--spacing-sm); border-top: 1px solid var(--color-border); }
.column-setting-row .el-checkbox { max-width: 100%; margin-right: 0; }
.column-setting-row :deep(.el-checkbox__label) { overflow-wrap: anywhere; white-space: normal; }
.column-controls { margin-left: auto; }
.column-controls .el-select { width: 112px; }
.column-controls .el-button { width: 44px; min-height: 44px; margin: 0; padding: 8px; }
</style>
