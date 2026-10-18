<template>
  <label class="report-field">
    <span>{{ label }}</span>
    <select v-if="kind === 'boolean' && operator !== 'in'" :value="String(modelValue)" :aria-label="label" :disabled="disabled" @change="booleanChange">
      <option value="true">true</option><option value="false">false</option>
    </select>
    <input v-else :value="raw" :disabled="disabled" :aria-invalid="!!error" :placeholder="operator === 'in' ? '[&quot;value1&quot;, &quot;value2&quot;]' : kind === 'datetime' ? '2026-10-01T00:00:00+08:00' : kind === 'date' ? '2026-10-01' : ''" @input="change" />
    <small v-if="error" role="alert">{{ error }}</small>
  </label>
</template>
<script setup lang="ts">
import { ref, watch } from 'vue'
import type { ReportFieldType } from '@/api/reportTypes'
import { uiText } from '@/i18n/uiText'
const props = withDefaults(defineProps<{ modelValue: unknown; label: string; kind?: ReportFieldType; operator?: string; disabled?: boolean }>(), { kind: 'text', operator: 'eq' })
const emit = defineEmits<{ 'update:modelValue': [unknown]; valid: [boolean] }>()
const raw = ref(''), error = ref('')
watch(() => [props.modelValue, props.operator], () => {
  raw.value = Array.isArray(props.modelValue) ? JSON.stringify(props.modelValue) : String(props.modelValue ?? '')
  error.value = ''; emit('valid', true)
}, { immediate: true })
function booleanChange(event: Event) { emit('update:modelValue', (event.target as HTMLSelectElement).value === 'true'); emit('valid', true) }
function change(event: Event) {
  raw.value = (event.target as HTMLInputElement).value
  let value: unknown = raw.value
  try {
    if (props.operator === 'in') {
      value = JSON.parse(raw.value)
      if (!Array.isArray(value) || value.length > 50) throw new Error()
    } else if (props.kind === 'integer') {
      value = Number(raw.value)
      if (!raw.value.trim() || !Number.isSafeInteger(value)) throw new Error()
    }
    error.value = ''; emit('valid', true); emit('update:modelValue', value)
  } catch { error.value = uiText('请输入有效值；in 使用最多50项的 JSON 数组'); emit('valid', false) }
}
</script>
