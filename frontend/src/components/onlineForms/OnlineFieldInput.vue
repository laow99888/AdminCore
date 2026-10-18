<template>
  <OnlineFileInput
    v-if="field.type === 'file'"
    :id="id"
    :label="field.label"
    :context="attachmentContext"
    :model-value="modelValue"
    :disabled="disabled"
    @update:model-value="emit('update:modelValue', $event)"
  />
  <OnlineRelationInput
    v-else-if="field.type === 'relation'"
    :id="id" :label="field.label" :context="attachmentContext" :model-value="modelValue" :disabled="disabled"
    @update:model-value="emit('update:modelValue', $event)"
  />
  <el-input
    v-else-if="['text', 'textarea', 'decimal'].includes(field.type)"
    :id="id"
    :aria-label="field.label"
    :model-value="String(modelValue ?? '')"
    :type="field.type === 'textarea' ? 'textarea' : 'text'"
    :inputmode="field.type === 'decimal' ? 'decimal' : undefined"
    :maxlength="field.max_length"
    :placeholder="field.placeholder"
    :disabled="disabled"
    @update:model-value="emit('update:modelValue', $event)"
  />
  <el-input-number
    v-else-if="field.type === 'number'"
    :id="id"
    :aria-label="field.label"
    :model-value="typeof modelValue === 'number' ? modelValue : undefined"
    :min="typeof field.min === 'number' ? field.min : undefined"
    :max="typeof field.max === 'number' ? field.max : undefined"
    @update:model-value="emit('update:modelValue', $event)"
  />
  <el-select
    v-else-if="['select', 'multiselect'].includes(field.type)"
    :id="id"
    :aria-label="field.label"
    :model-value="modelValue"
    :multiple="field.type === 'multiselect'"
    clearable
    :placeholder="field.placeholder"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-option
      v-for="option in field.options"
      :key="option"
      :value="option"
      :label="option"
    />
  </el-select>
  <el-date-picker
    v-else-if="field.type === 'date' || field.type === 'datetime'"
    :id="id"
    :aria-label="field.label"
    :model-value="typeof modelValue === 'string' ? modelValue : null"
    :type="field.type === 'date' ? 'date' : 'datetime'"
    :value-format="
      field.type === 'date' ? 'YYYY-MM-DD' : 'YYYY-MM-DDTHH:mm:ssZ'
    "
    @update:model-value="emit('update:modelValue', $event)"
  />
  <el-switch
    v-else-if="field.type === 'boolean'"
    :id="id"
    :aria-label="field.label"
    :model-value="modelValue === true"
    @update:model-value="emit('update:modelValue', $event)"
  />
</template>
<script setup lang="ts">
import type { OnlineFormField } from "@/api";
import type { OnlineAttachmentContext } from '@/api/onlineFormAttachments';
import OnlineFileInput from './OnlineFileInput.vue';
import OnlineRelationInput from './OnlineRelationInput.vue';
defineProps<{
  field: OnlineFormField;
  modelValue?: unknown;
  id: string;
  disabled?: boolean;
  attachmentContext?: OnlineAttachmentContext;
}>();
const emit = defineEmits<{ "update:modelValue": [value: unknown] }>();
</script>
<style scoped>
:deep(.el-input-number),
:deep(.el-date-editor),
.el-select {
  width: 100%;
  max-width: 100%;
}
</style>
