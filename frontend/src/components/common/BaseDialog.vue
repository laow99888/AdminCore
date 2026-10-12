<template>
  <el-dialog
    v-model="isVisible"
    :title="title || uiText('对话框')"
    :width="dialogWidth"
    :close-on-click-modal="false"
    class="base-dialog"
    @close="handleClose"
  >
    <!-- 对话框内容 -->
    <div class="dialog-content">
      <slot></slot>
    </div>

    <!-- 对话框底部 -->
    <template #footer>
      <div class="dialog-footer">
        <slot name="footer">
          <el-button v-if="showCancel" @click="handleCancel">{{ uiText("取消") }}</el-button>
          <el-button type="primary" :loading="loading" @click="handleConfirm">
            {{ confirmText || uiText('确认') }}
          </el-button>
        </slot>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { uiText } from "@/i18n/uiText"

import { computed, defineEmits } from 'vue'
import { useSidebar } from '../../composables/useSidebar'

interface Props {
  modelValue: boolean
  title?: string
  width?: string | number
  loading?: boolean
  confirmText?: string
  showCancel?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  title: '',
  width: '50%',
  loading: false,
  confirmText: '',
  showCancel: true,
})
const { isMobile } = useSidebar()
const dialogWidth = computed(() => isMobile.value ? 'calc(100vw - 24px)' : props.width)

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'confirm': []
  'cancel': []
  'close': []
}>()

const isVisible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})

const handleConfirm = () => {
  emit('confirm')
}

const handleCancel = () => {
  isVisible.value = false
  emit('cancel')
}

const handleClose = () => {
  emit('close')
}
</script>

<style scoped>
.dialog-content {
  max-height: 60vh;
  overflow-y: auto;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-md);
}

:deep(.el-dialog) {
  border-radius: var(--radius-xl);
}

:deep(.el-dialog__header) {
  border-bottom: 1px solid var(--color-border);
  padding: var(--spacing-lg);
}

:deep(.el-dialog__title) {
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

:deep(.el-dialog__body) {
  padding: var(--spacing-lg);
}

:deep(.el-dialog__footer) {
  border-top: 1px solid var(--color-border);
  padding: var(--spacing-lg);
}
</style>
