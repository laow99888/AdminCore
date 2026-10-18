<template>
  <div class="bulk-toolbar">
    <span role="status">{{ uiText('跨页已选') }} {{ selection.length }} / 100</span>
    <el-button :disabled="disabled || busy || !selection.length" @click="$emit('clear')">{{ uiText('清空选择') }}</el-button>
    <el-button type="danger" :disabled="disabled || busy || !selection.length" :loading="busy" @click="preview">{{ uiText('批量删除预检') }}</el-button>
    <span v-if="error" role="alert">{{ error }}</span>
    <BaseDialog v-model="opened" :title="uiText('批量删除预检')" width="760px" :loading="busy" :confirm-disabled="disabled || !token || confirmation !== '删除选中记录'" :confirm-text="uiText('删除选中记录')" @confirm="execute">
      <p>{{ uiText('仅删除预检通过的明确记录，不会自动选择其他页或后续新增数据。执行时重新核验权限、版本和业务约束。') }}</p>
      <p>{{ uiText('预检不执行业务扩展；实际执行仍可能被业务规则阻止。每项失败不会撤销其他成功项。预检15分钟内有效。') }}</p>
      <p role="status">{{ uiText('预检通过') }} {{ ready }} / {{ results.length }}<template v-if="finished">；{{ uiText('已删除') }} {{ deleted }}</template></p>
      <ul class="bulk-results"><li v-for="item in results" :key="item.id"><code>{{ item.id }}</code><span>{{ statusLabel(item.status) }}</span></li></ul>
      <label v-if="token">{{ uiText('输入“删除选中记录”确认') }}<el-input v-model="confirmation" :disabled="busy" :aria-label="uiText('输入“删除选中记录”确认')" /></label>
      <p v-if="error" role="alert">{{ error }}</p>
    </BaseDialog>
  </div>
</template>
<script setup lang="ts">
import './workbenchMessages'
import { onBeforeUnmount, ref, watch } from 'vue'
import { BaseDialog } from '@/components'
import { newIdempotencyKey } from '@/api'
import request, { type ApiResponse, errorMessage } from '@/api/request'
import { uiText } from '@/i18n/uiText'
import type { BulkResult, SelectedRecord } from './queryTypes'
const props = defineProps<{ endpoint: string; selection: SelectedRecord[]; disabled?: boolean }>()
const emit = defineEmits<{ clear: []; completed: []; busy: [value: boolean] }>()
const opened = ref(false), busy = ref(false), error = ref(''), token = ref(''), confirmation = ref(''), ready = ref(0), deleted = ref(0), finished = ref(false)
const results = ref<BulkResult[]>([])
let alive = true, generation = 0, key = ''
const controller = new AbortController()
watch(busy, value => emit('busy', value), { flush: 'sync' })
const statusLabel = (status: string) => uiText(({ ready: '预检通过', unavailable: '记录不可用', conflict: '版本已变化', blocked: '业务规则阻止', forbidden: '权限已变化', timeout: '操作超时', deleted: '已删除' } as Record<string, string>)[status] || status)
watch(() => JSON.stringify(props.selection), () => { generation++; token.value = ''; confirmation.value = '' })
async function preview() {
  if (busy.value || props.disabled || !props.selection.length) return
  const current = ++generation
  busy.value = true; error.value = ''; token.value = ''; finished.value = false; confirmation.value = ''; deleted.value = 0
  try {
    const response = await request.post<ApiResponse<{ items: BulkResult[]; ready: number; preview_token: string }>>(props.endpoint + 'bulk-preview/', { selection: props.selection }, { signal: controller.signal })
    if (!alive || generation !== current) return
    results.value = response.data.data.items; ready.value = response.data.data.ready; token.value = response.data.data.preview_token
    key = newIdempotencyKey('bulk-delete'); opened.value = true
  } catch (failure) { if (alive) error.value = errorMessage(failure, uiText('预检失败，请重试')) }
  finally { if (alive) busy.value = false }
}
async function execute() {
  if (busy.value || props.disabled || !token.value || confirmation.value !== '删除选中记录') return
  busy.value = true; error.value = ''
  try {
    const response = await request.post<ApiResponse<{ items: BulkResult[]; deleted: number }>>(props.endpoint + 'bulk-delete/', { preview_token: token.value, confirmation: confirmation.value }, { headers: { 'Idempotency-Key': key }, signal: controller.signal })
    if (!alive) return
    const byId = new Map(response.data.data.items.map(item => [item.id, item]))
    results.value = results.value.map(item => byId.get(item.id) || item); deleted.value = response.data.data.deleted
    token.value = ''; confirmation.value = ''; finished.value = true; emit('completed')
  } catch (failure) { if (alive) error.value = errorMessage(failure, uiText('删除失败，请刷新记录后重新预检；网络中断可用相同请求重试')) }
  finally { if (alive) busy.value = false }
}
onBeforeUnmount(() => { alive = false; generation++; controller.abort(); token.value = ''; results.value = [] })
</script>
<style scoped>
.bulk-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin: 12px 0; }
.bulk-results { padding: 0; list-style: none; }
.bulk-results li { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; padding: 8px 0; border-bottom: 1px solid var(--el-border-color); }
code { overflow-wrap: anywhere; }
[role=alert] { color: var(--el-color-danger); }
@media(max-width: 640px) { .bulk-toolbar :deep(button) { min-height: 44px; margin-left: 0; } }
</style>
