<template>
  <div class="field-policy-editor">
    <p>{{ uiText('未启用限制的资源沿用完整字段；已限制资源的多个角色按字段并集合并。') }}</p>
    <el-collapse>
      <el-collapse-item v-for="(fields, resource) in resources" :key="resource" :name="resource" :title="String(resource)">
        <el-switch :model-value="!!modelValue[resource]" :aria-label="uiText('限制字段') + ' ' + resource" @change="toggle(String(resource), $event === true)" />
        <template v-if="modelValue[resource]">
          <el-form-item v-for="action in (['read', 'write'] as const)" :key="action" :label="uiText(action === 'read' ? '可读字段' : '可写字段')">
            <el-select :model-value="modelValue[resource]![action]" multiple filterable :aria-label="String(resource) + ' ' + action" @update:model-value="change(String(resource), action, $event)">
              <el-option v-for="field in fields" :key="field" :label="field" :value="field" />
            </el-select>
          </el-form-item>
        </template>
      </el-collapse-item>
    </el-collapse>
    <el-alert v-if="!Object.keys(resources).length" :title="uiText('字段登记尚未加载，暂时不能修改字段策略')" type="warning" :closable="false" />
  </div>
</template>
<script setup lang="ts">
import { registerUiMessages, uiText } from '@/i18n/uiText'
registerUiMessages({ '未启用限制的资源沿用完整字段；已限制资源的多个角色按字段并集合并。': 'Resources without restrictions retain all fields. Explicit role policies are combined by union.', '限制字段': 'Restrict fields', '可读字段': 'Readable fields', '可写字段': 'Writable fields', '字段登记尚未加载，暂时不能修改字段策略': 'Field registry is unavailable. Policies cannot be edited yet.' })
registerUiMessages({ '字段权限': 'Field permissions' })
type Policies = Record<string, { read: string[]; write: string[] }>
const props = defineProps<{ modelValue: Policies; resources: Record<string, string[]> }>()
const emit = defineEmits<{ 'update:modelValue': [value: Policies] }>()
function toggle(resource: string, enabled: boolean) {
  const next = { ...props.modelValue }
  if (enabled) next[resource] = { read: [...props.resources[resource]!], write: [...props.resources[resource]!] }
  else delete next[resource]
  emit('update:modelValue', next)
}
function change(resource: string, action: 'read' | 'write', fields: string[]) {
  emit('update:modelValue', { ...props.modelValue, [resource]: { ...props.modelValue[resource]!, [action]: fields } })
}
</script>
<style scoped>
.field-policy-editor { width: 100%; }
.el-select { width: 100%; }
</style>
