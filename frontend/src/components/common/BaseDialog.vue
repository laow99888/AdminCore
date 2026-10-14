<template>
  <el-dialog
    v-model="isVisible"
    :title="title || uiText('对话框')"
    :width="dialogWidth"
    :close-on-click-modal="false"
    :before-close="guardClose"
    :close-on-press-escape="!loading"
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
          <el-button v-if="showCancel" :disabled="loading" @click="handleCancel">{{ uiText("取消") }}</el-button>
          <el-button type="primary" :loading="loading" :disabled="loading || confirmDisabled" @click="handleConfirm">
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
  confirmDisabled?: boolean
  confirmText?: string
  showCancel?: boolean
  beforeClose?: ((done: () => void) => void) | (() => Promise<boolean>)
}

const props = withDefaults(defineProps<Props>(), {
  title: '',
  width: '50%',
  loading: false,
  confirmDisabled: false,
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
  if (props.loading || props.confirmDisabled) return
  emit('confirm')
}

const handleCancel = () => {
  void guardClose(() => { isVisible.value = false; emit('cancel') })
}

async function guardClose(done: () => void) {
  if (props.loading) return
  if (!props.beforeClose) { done(); return }
  let completed = false
  const finish = () => { if (!completed && !props.loading) { completed = true; done() } }
  try {
    const result = await props.beforeClose(finish)
    if (result === true) finish()
  } catch { /* A failed close check preserves the dialog and its input. */ }
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
