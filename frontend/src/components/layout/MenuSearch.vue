<template>
  <div class="menu-search">
    <el-autocomplete v-model="query" class="desktop-search" :fetch-suggestions="suggest" :trigger-on-focus="false"
      :placeholder="uiText('搜索菜单')" :aria-label="uiText('搜索菜单')" clearable @select="select" />
    <button class="mobile-search" :aria-label="uiText('搜索菜单')" @click="opened = true"><Search :size="18" /></button>
    <el-dialog v-model="opened" :title="uiText('搜索菜单')" width="min(420px, 92vw)" append-to-body>
      <el-autocomplete v-model="query" :fetch-suggestions="suggest" :trigger-on-focus="false"
        :placeholder="uiText('搜索菜单')" :aria-label="uiText('搜索菜单')" clearable @select="select" />
      <p role="status">{{ notice }}</p>
    </el-dialog>
    <span class="sr-only" role="status">{{ notice }}</span>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Search } from 'lucide-vue-next'
import { menusApi, type MenuRow } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { useModuleStore } from '@/stores/modules'
import { canAccessPage } from '@/router/access'
import { uiText } from '@/i18n/uiText'

const auth = useAuthStore(), modules = useModuleStore(), router = useRouter()
const query = ref(''), notice = ref(''), opened = ref(false)
let generation = 0
type Item = { value: string; path: string; source: string }
let catalog: Item[] | undefined
let pending: Promise<Item[]> | undefined
const allowed = (path: string) => path.startsWith('/') && !path.startsWith('//') && modules.pathEnabled(path) &&
  canAccessPage(path, auth.user, modules.pagePermissions) && router.resolve(path).matched.some(route => route.meta.requiresAuth === true)
function reset() { generation++; catalog = undefined; pending = undefined; query.value = ''; notice.value = '' }
watch(() => JSON.stringify([auth.user?.id, auth.user?.permissions, auth.user?.is_staff, auth.user?.is_superuser, modules.config]), reset)
window.addEventListener('admincore:menus-updated', reset)
onBeforeUnmount(() => { reset(); window.removeEventListener('admincore:menus-updated', reset) })
async function suggest(text: string, done: (items: Item[]) => void) {
  const current = generation
  if (!text.trim() || !auth.user) { notice.value = ''; done([]); return }
  try {
    if (!catalog) {
      pending ??= menusApi.myMenu().then(rows => {
        const flatten = (items: MenuRow[]): Item[] => items.flatMap(item => [
          ...(item.is_visible === false ? [] : [{ value: item.name, source: item.name, path: item.path }]),
          ...flatten(item.children || []),
        ])
        return flatten(rows)
      })
      const loaded = await pending
      if (current !== generation) { done([]); return }
      catalog = loaded
    }
    const needle = text.trim().toLocaleLowerCase()
    const results = catalog.filter(item => allowed(item.path)).map(item => ({ ...item, value: uiText(item.source) }))
      .filter(item => `${item.value} ${item.source} ${item.path}`.toLocaleLowerCase().includes(needle)).slice(0, 20)
    notice.value = results.length ? '' : uiText('没有匹配的菜单')
    done(results)
  } catch {
    if (current === generation) { pending = undefined; notice.value = uiText('菜单搜索加载失败，请重试') }
    done([])
  }
}
function select(item: Record<string, unknown>) {
  if (typeof item.path !== 'string' || !allowed(item.path)) return
  opened.value = false
  query.value = ''
  void router.push(item.path)
}
</script>

<style scoped>
.menu-search { width: 200px; }
.desktop-search { width: 100%; }
.mobile-search { display: none; width: 44px; height: 44px; align-items: center; justify-content: center; border: 0; border-radius: var(--radius-lg); background: var(--color-bg-elevated); color: var(--color-text-primary); cursor: pointer; }
.mobile-search:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
@media (max-width: 768px) { .menu-search { width: 44px; } .desktop-search { display: none; } .mobile-search { display: flex; } }
</style>
