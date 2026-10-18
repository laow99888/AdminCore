<template>
  <div class="working-calendar">
    <el-switch :model-value="!!modelValue" :disabled="disabled" :aria-label="uiText('仅累计工作时段')" @update:model-value="toggle" />
    <span>{{ uiText('仅累计工作时段') }}</span>
    <template v-if="modelValue">
      <label>{{ uiText('日历时区') }}<el-input :model-value="modelValue.timezone" :disabled="disabled" :aria-label="uiText('日历时区')" @update:model-value="change('timezone', $event)" /></label>
      <el-checkbox-group :model-value="modelValue.weekdays" :disabled="disabled" :aria-label="uiText('工作日')" @update:model-value="change('weekdays', $event)">
        <el-checkbox v-for="day in 7" :key="day" :value="day">{{ day }}</el-checkbox>
      </el-checkbox-group>
      <label>{{ uiText('工作开始时间') }}<el-input :model-value="modelValue.start" :disabled="disabled" placeholder="09:00" :aria-label="uiText('工作开始时间')" @update:model-value="change('start', $event)" /></label>
      <label>{{ uiText('工作结束时间') }}<el-input :model-value="modelValue.end" :disabled="disabled" placeholder="18:00" :aria-label="uiText('工作结束时间')" @update:model-value="change('end', $event)" /></label>
      <label>{{ uiText('休息日期（每行一个）') }}<el-input :model-value="modelValue.closed_dates.join('\n')" type="textarea" :disabled="disabled" placeholder="2026-10-01" :aria-label="uiText('休息日期（每行一个）')" @update:model-value="dates('closed_dates', $event)" /></label>
      <label>{{ uiText('补班日期（每行一个）') }}<el-input :model-value="modelValue.extra_dates.join('\n')" type="textarea" :disabled="disabled" placeholder="2026-10-10" :aria-label="uiText('补班日期（每行一个）')" @update:model-value="dates('extra_dates', $event)" /></label>
      <small>{{ uiText('1为周一，7为周日；同日时段至少60分钟，日期格式YYYY-MM-DD；日历随发布版本冻结。') }}</small>
    </template>
  </div>
</template>
<script setup lang="ts">
import { uiText } from '@/i18n/uiText'
import type { WorkingCalendar } from './workingCalendar'
import './messages'
const props = defineProps<{ modelValue: WorkingCalendar | null; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: WorkingCalendar | null] }>()
function toggle(enabled: string | number | boolean) {
  if (!props.disabled) emit('update:modelValue', enabled ? { timezone: 'Asia/Shanghai', weekdays: [1, 2, 3, 4, 5], start: '09:00', end: '18:00', closed_dates: [], extra_dates: [] } : null)
}
function change(key: keyof WorkingCalendar, value: unknown) {
  if (!props.disabled && props.modelValue) emit('update:modelValue', { ...props.modelValue, [key]: value })
}
function dates(key: 'closed_dates' | 'extra_dates', value: string) { change(key, value.split('\n').map(row => row.trim()).filter(Boolean)) }
</script>
<style scoped>
.working-calendar { display: grid; gap: 6px; min-width: 0; }
label { display: grid; gap: 4px; }
small { overflow-wrap: anywhere; color: var(--el-text-color-secondary); }
</style>
