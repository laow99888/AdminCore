<template>
  <button class="business-search-trigger" :aria-label="text('业务搜索')" @click="opened = true"><Search :size="18" /></button>
  <el-dialog v-model="opened" :title="text('业务搜索')" width="min(680px, 94vw)" append-to-body @closed="reset">
    <form class="business-search-form" @submit.prevent="run">
      <el-input v-model="query" :aria-label="text('业务关键词')" :placeholder="text('输入2至80个字符搜索业务记录')" maxlength="80" clearable />
      <el-button native-type="submit" :disabled="query.trim().length < 2 || loading">{{ text('搜索') }}</el-button>
    </form>
    <p role="status" aria-live="polite">{{ loading ? text('正在搜索') : notice }}</p>
    <el-button v-if="failed" @click="run">{{ text('重试') }}</el-button>
    <section v-for="group in groups" :key="group.source" class="business-search-group" :aria-label="group.title">
      <h3>{{ group.title }}</h3>
      <ul><li v-for="item in group.items" :key="item.id">
        <button class="business-search-record" @click="select(group, item)"><strong>{{ item.title }}</strong>
          <span v-for="(value, index) in item.values" :key="index">{{ value.label }}：{{ value.value }}</span>
        </button>
      </li></ul>
      <p v-if="group.has_more">{{ text('仅显示最近5条，请细化关键词或进入业务列表筛选') }}</p>
    </section>
  </el-dialog>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Search } from 'lucide-vue-next'
import request, { type ApiResponse } from '@/api/request'
import { useAuthStore } from '@/stores/auth'
import { useModuleStore } from '@/stores/modules'
import { useTenantStore } from '@/stores/tenants'
import { sessionIdentity } from '@/auth/sessionIdentity'
import { canAccessPage } from '@/router/access'
import { registerUiMessages, uiText } from '@/i18n/uiText'

registerUiMessages({
  '业务搜索': 'Business search', '业务关键词': 'Business keywords',
  '输入2至80个字符搜索业务记录': 'Enter 2–80 characters to search business records',
  '正在搜索': 'Searching', '没有匹配的授权业务记录': 'No matching authorized business records',
  '业务搜索失败，请重试': 'Business search failed. Please retry.',
  '仅显示最近5条，请细化关键词或进入业务列表筛选': 'Only the latest 5 matches are shown. Refine your keywords or filter the business list.',
  '最多搜索8个来源，请细化到业务列表查询': 'Search covers up to 8 sources. Use the business list for more sources.',
})
const text = uiText
interface SearchRecord { id: string; title: string; values: { label: string; value: string }[] }
interface SearchGroup { source: string; title: string; path: string; items: SearchRecord[]; has_more: boolean }
interface SearchResult { groups: SearchGroup[]; sources_limited: boolean }
const auth = useAuthStore(), modules = useModuleStore(), tenants = useTenantStore(), router = useRouter()
const opened = ref(false), query = ref(''), loading = ref(false), failed = ref(false), notice = ref('')
const groups = ref<SearchGroup[]>([])
let generation = 0, controller: AbortController | undefined, timer: ReturnType<typeof setTimeout> | undefined
function invalidate() {
  generation++; controller?.abort(); controller = undefined
  clearTimeout(timer); timer = undefined
  groups.value = []; loading.value = false; failed.value = false; notice.value = ''
}
function reset() { invalidate(); query.value = '' }
const allowed = (path: string) => !!auth.user && !auth.user.must_change_password && path.startsWith('/') && !path.startsWith('//') && modules.pathEnabled(path) &&
  canAccessPage(path, auth.user, modules.pagePermissions) && router.resolve(path).matched.some(route => route.meta.requiresAuth === true)
watch(() => JSON.stringify([auth.user?.id, sessionIdentity(auth.token), auth.user?.permissions, auth.user?.is_staff,
  auth.user?.is_superuser, auth.user?.must_change_password, tenants.currentId, modules.config]), () => { opened.value = false; reset() }, { flush: 'sync' })
watch(query, () => { invalidate(); if (opened.value && query.value.trim().length >= 2) timer = setTimeout(() => { void run() }, 300) }, { flush: 'sync' })
watch(opened, value => { if (!value) reset() }, { flush: 'sync' })
onBeforeUnmount(reset)
async function run() {
  invalidate()
  const keyword = query.value.trim(), current = generation
  if (!opened.value || !auth.user || auth.user.must_change_password || keyword.length < 2 || keyword.length > 80) return
  controller = new AbortController(); loading.value = true
  try {
    const response = await request.get<ApiResponse<SearchResult>>('/business-search/', { params: { q: keyword }, signal: controller.signal })
    if (current !== generation || !opened.value) return
    groups.value = response.data.data.groups.filter(group => allowed(group.path))
    notice.value = response.data.data.sources_limited ? text('最多搜索8个来源，请细化到业务列表查询') :
      groups.value.length ? '' : text('没有匹配的授权业务记录')
  } catch {
    if (current === generation) { failed.value = true; notice.value = text('业务搜索失败，请重试') }
  } finally { if (current === generation) loading.value = false }
}
function select(group: SearchGroup, item: SearchRecord) {
  if (!allowed(group.path) || !/^[0-9a-f-]{36}$/i.test(item.id)) return
  opened.value = false
  void router.push({ path: group.path, query: { record: item.id } })
}
</script>

<style scoped>
.business-search-trigger { width: 44px; height: 44px; display: inline-flex; align-items: center; justify-content: center; border: 0; border-radius: var(--radius-lg); background: var(--color-bg-elevated); color: var(--color-text-primary); cursor: pointer; flex-shrink: 0; }
.business-search-trigger:focus-visible, .business-search-record:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }
.business-search-form { display: flex; gap: var(--spacing-sm); }
.business-search-form .el-input { min-width: 0; }
.business-search-group ul { padding: 0; list-style: none; }
.business-search-record { width: 100%; text-align: start; display: grid; gap: 4px; padding: var(--spacing-sm); margin: 4px 0; border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-bg-elevated); color: var(--color-text-primary); overflow-wrap: anywhere; cursor: pointer; }
.business-search-record span { font-size: 12px; color: var(--color-text-secondary); }
</style>
