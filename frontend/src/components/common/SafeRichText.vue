<template>
  <div :aria-label="label" role="region" class="safe-rich-text">
    <p v-if="failed" role="alert">{{ uiText('正文超出安全显示限制，请联系管理员。') }}</p>
    <!-- Only the local strict sanitizer result enters v-html. -->
    <!-- eslint-disable-next-line vue/no-v-html -->
    <div v-else-if="format === 'html'" v-html="safeHtml"></div>
    <div v-else class="plain-text">{{ content }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { sanitizeRichText } from '@/utils/richText'
import { uiText } from '@/i18n/uiText'
const props = withDefaults(defineProps<{ content?: string; format?: 'plain' | 'html'; label?: string }>(), { content: '', format: 'plain', label: '' })
const cleaned = computed(() => { try { return { html: props.format === 'html' ? sanitizeRichText(props.content) : '', failed: false } } catch { return { html: '', failed: true } } })
const safeHtml = computed(() => cleaned.value.html), failed = computed(() => cleaned.value.failed)
</script>

<style scoped>
.safe-rich-text { line-height: 1.7; overflow-wrap: anywhere; min-width: 0; }
.plain-text { white-space: pre-wrap; }
.safe-rich-text :deep(pre) { white-space: pre-wrap; background: var(--color-bg-elevated); padding: var(--spacing-md); border-radius: var(--radius-md); }
.safe-rich-text :deep(blockquote) { margin-inline: 0; border-left: 3px solid var(--color-border); padding-left: var(--spacing-md); color: var(--color-text-secondary); }
.safe-rich-text :deep(a) { color: var(--color-primary); text-decoration: underline; }
.safe-rich-text :deep(h2), .safe-rich-text :deep(h3) { line-height: 1.4; }
</style>
