<template>
  <section class="watermark-settings" aria-labelledby="watermark-setting-label">
    <div class="watermark-setting-row">
      <div class="watermark-description">
        <div id="watermark-setting-label" class="watermark-setting-label">{{ uiText('页面水印') }}</div>
        <p id="watermark-setting-description">{{ uiText('在已登录页面显示 AdminCore 与当前用户名；仅保存在本浏览器，默认关闭。') }}</p>
      </div>
      <el-switch :model-value="watermark.enabled" :aria-label="uiText('启用页面水印')" aria-describedby="watermark-setting-description" @change="changeEnabled" />
    </div>
    <p class="watermark-limit">{{ uiText('水印用于页面标识，不能阻止截图或替代访问权限。') }}</p>
    <p v-if="!watermark.persistenceAvailable" class="watermark-warning" role="status">{{ uiText('浏览器无法保存水印偏好，当前设置仅在本次页面会话内生效。') }}</p>
  </section>
</template>

<script setup lang="ts">
import { uiText } from '@/i18n/uiText'
import { useWatermarkStore } from '@/stores/watermark'

const watermark = useWatermarkStore()
function changeEnabled(value: string | number | boolean) { watermark.setEnabled(value === true) }
</script>

<style scoped>
.watermark-settings { padding: var(--spacing-md) 0; }
.watermark-setting-row { display: flex; align-items: center; justify-content: space-between; gap: var(--spacing-md); }
.watermark-description { min-width: 0; }
.watermark-setting-label { font-weight: var(--font-weight-semibold); color: var(--color-text-primary); }
.watermark-settings p { margin: var(--spacing-xs) 0 0; color: var(--color-text-secondary); font-size: var(--font-size-sm); line-height: 1.5; overflow-wrap: anywhere; }
.watermark-setting-row :deep(.el-switch) { min-width: 44px; min-height: 44px; flex-shrink: 0; }
.watermark-settings .watermark-warning { color: var(--color-warning); }
</style>
