<template>
  <div class="rich-editor-loader" :aria-busy="loading">
    <p v-if="loading" role="status">{{ uiText('正在加载富文本编辑器') }}</p>
    <div v-else-if="failed" role="alert"><p>{{ uiText('富文本编辑器加载失败，请重试。') }}</p><el-button :disabled="disabled" @click="load">{{ uiText('重试加载编辑器') }}</el-button></div>
    <component :is="core" v-else-if="core" :model-value="modelValue" :label="label" :disabled="disabled" @update:model-value="emit('update:modelValue', $event)" @invalid="emit('invalid', $event)" @ready="emit('ready', true)" />
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, shallowRef, ref, type Component } from 'vue'
import { uiText } from '@/i18n/uiText'
defineProps<{ modelValue: string; label: string; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: string]; invalid: [value: string]; ready: [value: boolean] }>()
const core = shallowRef<Component>(), loading = ref(false), failed = ref(false)
let alive = true
async function load() {
  if (loading.value) return
  loading.value = true; failed.value = false; emit('ready', false)
  try { const value = await import('./RichTextEditorCore.vue'); if (alive) core.value = value.default }
  catch { if (alive) failed.value = true }
  finally { if (alive) loading.value = false }
}
onMounted(load)
onBeforeUnmount(() => { alive = false; core.value = undefined; emit('ready', false) })
</script>

<style scoped>
.rich-editor-loader { width: 100%; min-width: 0; }
</style>
