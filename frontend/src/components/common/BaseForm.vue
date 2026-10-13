<template>
  <el-form
    ref="formRef"
    :model="modelValue"
    :rules="rules"
    :disabled="loading"
    :aria-busy="loading"
    label-width="auto"
    class="base-form"
    :class="{ 'is-loading': loading }"
    @submit.prevent="handleSubmit"
  >
    <!-- 表单字段 -->
    <el-form-item
      v-for="field in fields"
      :key="field.prop"
      :prop="field.prop"
      :label="field.label"
      :required="field.required"
    >
      <!-- 文本输入 -->
      <el-input
        v-if="field.type === 'text' || field.type === 'email' || field.type === 'password'"
        v-model="formModel[field.prop]"
        :type="field.type"
        :placeholder="field.placeholder"
        :disabled="field.disabled"
        :clearable="field.clearable !== false"
        :show-password="field.type === 'password'"
      />

      <!-- 数字输入 -->
      <el-input-number
        v-else-if="field.type === 'number'"
        v-model="formModel[field.prop]"
        :placeholder="field.placeholder"
        :disabled="field.disabled"
      />

      <!-- 下拉选择 -->
      <el-select
        v-else-if="field.type === 'select'"
        v-model="formModel[field.prop]"
        :placeholder="field.placeholder"
        :disabled="field.disabled"
        :clearable="field.clearable !== false"
      >
        <el-option
          v-for="opt in field.options"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>

      <!-- 多选 -->
      <el-select
        v-else-if="field.type === 'multiselect'"
        v-model="formModel[field.prop]"
        :placeholder="field.placeholder"
        :disabled="field.disabled"
        multiple
        :clearable="field.clearable !== false"
      >
        <el-option
          v-for="opt in field.options"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>

      <!-- 日期选择 -->
      <el-date-picker
        v-else-if="field.type === 'date'"
        v-model="formModel[field.prop]"
        type="date"
        :placeholder="field.placeholder"
        :disabled="field.disabled"
      />

      <!-- 日期时间选择 -->
      <el-date-picker
        v-else-if="field.type === 'datetime'"
        v-model="formModel[field.prop]"
        type="datetime"
        :placeholder="field.placeholder"
        :disabled="field.disabled"
      />

      <!-- 开关 -->
      <el-switch
        v-else-if="field.type === 'switch'"
        v-model="formModel[field.prop]"
        :disabled="field.disabled"
      />

      <!-- 复选框 -->
      <el-checkbox
        v-else-if="field.type === 'checkbox'"
        v-model="formModel[field.prop]"
        :label="field.checkboxLabel"
        :disabled="field.disabled"
      />

      <!-- 文本域 -->
      <el-input
        v-else-if="field.type === 'textarea'"
        v-model="formModel[field.prop]"
        type="textarea"
        :placeholder="field.placeholder"
        :disabled="field.disabled"
        :rows="field.rows || 4"
      />
    </el-form-item>

    <!-- 操作按钮 -->
    <div class="form-actions">
      <el-button type="primary" native-type="submit" :loading="loading" :disabled="loading">
        {{ submitText || uiText('提交') }}
      </el-button>
      <el-button :disabled="loading" @click="handleReset">{{ resetText || uiText('重置') }}</el-button>
      <slot name="actions"></slot>
    </div>
  </el-form>
</template>

<script setup lang="ts">
import { uiText } from "@/i18n/uiText"

import { ref, toRaw } from 'vue'
import type { FormInstance } from 'element-plus'

type FieldType = 'text' | 'email' | 'password' | 'number' | 'select' | 'multiselect' | 'date' | 'datetime' | 'switch' | 'checkbox' | 'textarea'

interface FormField<T = any> {
  prop: Extract<keyof T, string>
  label: string
  type: FieldType
  placeholder?: string
  required?: boolean
  disabled?: boolean
  clearable?: boolean
  options?: Array<{ label: string; value: any }>
  checkboxLabel?: string
  rows?: number
}

interface Props<T = any> {
  modelValue: T
  fields: FormField<T>[]
  rules?: Record<string, any>
  loading?: boolean
  submitText?: string
  resetText?: string
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  submitText: '',
  resetText: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: any]
  'submit': [value: any]
}>()

const formRef = ref<FormInstance>()
const initialValues = structuredClone(toRaw(props.modelValue))
const formModel = new Proxy({} as Record<string, any>, {
  get: (_target, key: string) => props.modelValue[key],
  set: (_target, key: string, value) => {
    emit('update:modelValue', { ...props.modelValue, [key]: value })
    return true
  },
})

const handleSubmit = async () => {
  if (props.loading) return
  try {
    const valid = await formRef.value?.validate()
    if (valid !== false) emit('submit', props.modelValue)
  } catch {
    // Element Plus 在字段旁显示校验错误；不要提交或制造未处理 Promise。
  }
}

const handleReset = () => {
  if (props.loading) return
  emit('update:modelValue', structuredClone(initialValues))
  formRef.value?.clearValidate()
}
</script>

<style scoped>
.base-form {
  width: 100%;
}

.base-form.is-loading {
  opacity: 0.6;
  pointer-events: none;
}

.form-actions {
  display: flex;
  gap: var(--spacing-md);
  margin-top: var(--spacing-xl);
}

:deep(.el-form-item__label) {
  color: var(--color-text-primary);
  font-weight: var(--font-weight-semibold);
}

:deep(.el-input__wrapper),
:deep(.el-select__wrapper),
:deep(.el-date-picker__editor) {
  background-color: var(--color-bg-elevated);
  border-color: var(--color-border);
}

:deep(.el-input__wrapper:hover),
:deep(.el-select__wrapper:hover) {
  border-color: var(--color-primary-500);
}
</style>
