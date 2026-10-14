<template>
  <AppLayout>
    <div class="cache-page">
      <div class="page-heading">
        <div><h1>{{ uiText('缓存管理') }}</h1><p>{{ uiText('仅清理登记的业务缓存；不清空会话、锁、队列或限流数据。') }}</p></div>
        <BaseButton size="large" variant="ghost" :loading="loading" :disabled="busy || loading" @click="load">{{ uiText('刷新') }}</BaseButton>
      </div>
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon role="alert" />
      <el-alert v-if="notice" :title="notice" type="success" :closable="false" show-icon role="status" />
      <BaseCard v-if="loading"><p role="status">{{ uiText('正在加载缓存目录') }}</p><el-skeleton :rows="3" animated /></BaseCard>
      <template v-if="catalog">
        <el-alert :title="backendLabel(catalog.backend)" type="info" :closable="false" show-icon />
        <p class="hint">{{ uiText('候选数量来自数据库当前版本，不代表实际缓存存量或删除数量。历史版本最多保留 300 秒。') }}</p>
        <el-empty v-if="!catalog.namespaces.length" :description="uiText('暂无登记的缓存')" />
        <div class="namespace-grid">
          <BaseCard v-for="row in catalog.namespaces" :key="row.namespace" :title="namespaceLabel(row.namespace)">
            <dl><div><dt>{{ uiText('所属模块') }}</dt><dd>{{ uiText('系统管理') }}</dd></div>
              <div><dt>{{ uiText('候选数量') }}</dt><dd>{{ row.over_limit ? `>${catalog.limit}` : row.candidate_count }}</dd></div></dl>
            <p class="hint">{{ uiText('清理不修改业务数据，后续读取按数据库当前版本重建缓存。') }}</p>
            <p v-if="row.over_limit" role="alert">{{ uiText('候选数量超过单次上限，此入口不允许清理。') }}</p>
            <BaseButton v-if="canClear(row.namespace)" size="large" variant="ghost" :disabled="busy || loading || row.over_limit || catalog.backend === 'unsupported'" @click="prepare(row.namespace)">{{ uiText('预览清理 {p0}', { p0: namespaceLabel(row.namespace) }) }}</BaseButton>
          </BaseCard>
        </div>
      </template>
      <BaseDialog v-model="dialog" :title="uiText('确认缓存清理')" width="520px" :before-close="guardClose" :close-on-press-escape="!busy" @close="discard">
        <template v-if="preview">
          <p>{{ namespaceLabel(preview.namespace) }} · {{ uiText('候选数量') }}: {{ preview.candidate_count }}</p>
          <p>{{ backendLabel(preview.backend) }}</p>
          <p>{{ uiText('清理不修改业务数据，后续读取按数据库当前版本重建缓存。') }}</p>
          <p role="status">{{ expired ? uiText('预览已过期，请取消后重新预览。') : uiText('预览有效期剩余 {p0} 秒', { p0: seconds }) }}</p>
        </template>
        <template #footer>
          <BaseButton size="large" variant="ghost" :disabled="busy" @click="dialog = false">{{ uiText('取消') }}</BaseButton>
          <BaseButton size="large" variant="primary" :loading="busy" :disabled="busy || expired || !preview || !canClear(preview.namespace)" @click="execute">{{ uiText('确认清理') }}</BaseButton>
        </template>
      </BaseDialog>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import AppLayout from '@/components/layout/AppLayout.vue'
import { BaseButton, BaseCard, BaseDialog } from '@/components'
import { cacheApi, type CacheCatalog, type CacheNamespace, type CacheBackend, type CachePreview } from '@/api/cache'
import { useAuthStore } from '@/stores/auth'
import { uiText } from '@/i18n/uiText'

const auth = useAuthStore()
const catalog = ref<CacheCatalog | null>(null), preview = ref<CachePreview | null>(null)
const loading = ref(false), busy = ref(false), dialog = ref(false), error = ref(''), notice = ref('')
const deadline = ref(0), now = ref(Date.now())
const seconds = computed(() => Math.max(0, Math.ceil((deadline.value - now.value) / 1000)))
const expired = computed(() => seconds.value <= 0)
let alive = true
const timer = window.setInterval(() => { now.value = Date.now() }, 1000)
function namespaceLabel(namespace: CacheNamespace) { return uiText(namespace === 'configuration' ? '系统参数缓存' : '字典选项缓存') }
function backendLabel(backend: CacheBackend) { return uiText(backend === 'shared' ? '共享缓存：影响使用相同缓存配置的进程。' : backend === 'in_process' ? '进程内缓存：仅影响本次请求所在进程，其他进程不会同步清理。' : '当前缓存后端不支持此清理入口。') }
function canClear(namespace: CacheNamespace) { return auth.can('cache:clear') && auth.can(namespace === 'configuration' ? 'config:update' : 'dictionary:update') }
function discard() { if (!busy.value) { preview.value = null; deadline.value = 0 } }
function guardClose(done: () => void) { if (!busy.value) done() }
async function load() {
  if (loading.value || busy.value) return
  loading.value = true; error.value = ''; catalog.value = null
  try { const result = await cacheApi.catalog(); if (alive) catalog.value = result }
  catch { if (alive) error.value = uiText('缓存目录加载失败，请刷新重试。') }
  finally { if (alive) loading.value = false }
}
async function prepare(namespace: CacheNamespace) {
  if (busy.value || !canClear(namespace)) return
  busy.value = true; error.value = ''; notice.value = ''; preview.value = null
  try {
    const result = await cacheApi.preview(namespace)
    if (alive) { preview.value = result; now.value = Date.now(); deadline.value = now.value + result.expires_in * 1000; dialog.value = true }
  } catch { if (alive) error.value = uiText('无法预览清理，请刷新目录后重试。') }
  finally { if (alive) busy.value = false }
}
async function execute() {
  if (busy.value || expired.value || !preview.value || !canClear(preview.value.namespace)) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    await cacheApi.clear(preview.value)
    if (alive) notice.value = uiText('限定范围的清理已完成；并发读取可能重新填充缓存。')
  } catch { if (alive) error.value = uiText('清理未确认，可能部分完成；请重新预览，不要依赖缓存保持为空。') }
  finally { if (alive) { busy.value = false; dialog.value = false; discard(); await loadAfterAction() } }
}
async function loadAfterAction() {
  // Preserve the action outcome while refreshing the candidate catalog.
  const actionError = error.value
  await load()
  if (actionError) error.value = actionError
}
void load()
onBeforeUnmount(() => { alive = false; window.clearInterval(timer); preview.value = null })
</script>

<style scoped>
.cache-page { display: grid; gap: var(--spacing-lg); min-width: 0; }
.page-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--spacing-md); }
.page-heading > div { min-width: 0; }
h1 { font-size: var(--font-size-xl); margin: 0 0 var(--spacing-sm); }
p { line-height: 1.6; overflow-wrap: anywhere; }
.hint, .page-heading p, dt { color: var(--color-text-secondary); font-size: var(--font-size-sm); }
.namespace-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--spacing-lg); }
dl { display: flex; flex-wrap: wrap; gap: var(--spacing-xl); }
dd { margin: var(--spacing-sm) 0; }
@media (max-width: 768px) { .namespace-grid { grid-template-columns: 1fr; } }
</style>
