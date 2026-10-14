<template>
  <main v-if="failed" class="app-error-boundary" aria-labelledby="app-error-heading">
    <section class="error-content" role="alert">
      <h1 id="app-error-heading" ref="heading" tabindex="-1">{{ uiText('页面发生错误') }}</h1>
      <p>{{ uiText('当前页面无法继续显示，请重试或返回首页。') }}</p>
      <p class="recovery-note">{{ uiText('重试会重新打开当前页面，当前未保存的输入将丢失。') }}</p>
      <div class="error-actions">
        <button type="button" class="retry-button" @click="retry">{{ uiText('重新打开当前页面') }}</button>
        <button type="button" @click="home">{{ uiText('返回首页') }}</button>
      </div>
    </section>
  </main>
  <div v-else :key="generation" class="boundary-content"><slot /></div>
</template>

<script setup lang="ts">
import { nextTick, onErrorCaptured, ref, watch } from 'vue'
import { uiText } from '@/i18n/uiText'
import { errorReporter, type ErrorReporter } from '@/utils/errorReporting'

const props = defineProps<{ resetKey: string; routePath: string; reporter?: ErrorReporter }>()
const emit = defineEmits<{ retry: []; home: [] }>()
const failed = ref(false)
const generation = ref(0)
const heading = ref<HTMLElement>()
function reset() { failed.value = false; generation.value++ }
function captureError() {
  if (failed.value) return
  failed.value = true
  void nextTick(() => heading.value?.focus())
}
onErrorCaptured(() => {
  ;(props.reporter ?? errorReporter).report('vue', props.routePath)
  captureError()
  return false
})
function retry() { reset(); emit('retry') }
function home() { if (props.routePath === '/') reset(); emit('home') }
// Healthy navigation belongs to RouterView/KeepAlive; only a failed subtree needs rebuilding.
watch(() => props.resetKey, () => { if (failed.value) reset() })
defineExpose({ captureError, resetError: reset })
</script>

<style scoped>
.boundary-content { min-width: 0; }
.app-error-boundary { display: grid; place-items: center; min-height: 100dvh; padding: var(--spacing-lg); background: var(--color-bg-page); color: var(--color-text-primary); }
.error-content { max-width: 560px; text-align: center; overflow-wrap: anywhere; }
h1 { font-size: clamp(24px, 5vw, 36px); margin: 0 0 var(--spacing-lg); }
h1:focus { outline: none; }
p { color: var(--color-text-secondary); line-height: 1.7; }
.recovery-note { font-size: var(--font-size-sm); }
.error-actions { display: flex; justify-content: center; gap: var(--spacing-md); flex-wrap: wrap; margin-top: var(--spacing-xl); }
button { min-height: 44px; padding: var(--spacing-sm) var(--spacing-lg); border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-bg-elevated); color: var(--color-text-primary); font: inherit; cursor: pointer; }
button:focus-visible { outline: 2px solid var(--color-primary-500); outline-offset: 3px; }
.retry-button { background: var(--color-primary-700); border-color: var(--color-primary-700); color: var(--color-gray-50); }
</style>
