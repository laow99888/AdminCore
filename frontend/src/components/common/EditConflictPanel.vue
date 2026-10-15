<template>
  <section class="edit-conflict" role="region" :aria-label="uiText('编辑冲突')" :aria-busy="loading">
    <el-alert :title="uiText('记录已被修改，输入已保留；请比较服务器最新值后再决定是否载入。')" type="warning" :closable="false" />
    <div class="conflict-actions">
      <el-button :loading="loading" :disabled="disabled || loading" @click="emit('inspect')">{{ uiText('查看服务器最新值') }}</el-button>
      <el-button v-if="serverVersion !== undefined" :disabled="disabled || loading" @click="emit('apply')">{{ uiText('载入服务器最新值（替换当前输入）') }}</el-button>
    </div>
    <p v-if="failed" role="alert">{{ uiText('最新值加载失败或已无权限，当前输入未改变。') }}</p>
    <p v-if="serverVersion !== undefined">{{ uiText('当前编辑版本：{p0}；服务器版本：{p1}', { p0: version, p1: serverVersion }) }}</p>
    <div v-if="serverVersion !== undefined" class="comparison-scroll">
      <table><caption>{{ uiText('当前输入与服务器最新值') }}</caption><thead><tr><th scope="col">{{ uiText('字段') }}</th><th scope="col">{{ uiText('当前输入') }}</th><th scope="col">{{ uiText('服务器最新值') }}</th></tr></thead>
        <tbody><tr v-for="row in rows" :key="row.label"><th scope="row">{{ row.label }}</th><td>{{ row.local }}</td><td>{{ row.server }}</td></tr></tbody>
      </table>
    </div>
  </section>
</template>

<script setup lang="ts">
import { uiText, registerUiMessages } from '@/i18n/uiText'
import { editConflictMessages } from '@/i18n/editConflictMessages'
registerUiMessages(editConflictMessages)
defineProps<{ loading: boolean; failed: boolean; disabled?: boolean; version: number | string;
  serverVersion?: number | string; rows: Array<{ label: string; local: string; server: string }> }>()
const emit = defineEmits<{ inspect: []; apply: [] }>()
</script>

<style scoped>
.edit-conflict { min-width: 0; margin-bottom: var(--spacing-md); }
.conflict-actions { display: flex; flex-wrap: wrap; gap: var(--spacing-sm); margin-top: var(--spacing-sm); }
.conflict-actions .el-button { height: auto; min-height: 44px; margin: 0; white-space: normal; }
.comparison-scroll { max-width: 100%; overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: var(--font-size-sm); }
th, td { text-align: left; vertical-align: top; border: 1px solid var(--color-border); padding: var(--spacing-sm); overflow-wrap: anywhere; min-width: 90px; }
caption { text-align: left; margin-bottom: var(--spacing-xs); }
</style>
