<template>
  <section class="file-library" :aria-label="uiText('我的文件整理')" :aria-busy="loading">
    <p class="library-hint">{{ uiText('目录和标签仅自己可见，不改变文件授权。') }}</p>
    <el-alert v-if="failed" :title="uiText('无法读取整理信息，请重试')" type="error" :closable="false">
      <el-button @click="load">{{ uiText('重试') }}</el-button>
    </el-alert>
    <form class="library-controls" @submit.prevent="applyFilter">
      <label>{{ uiText('个人目录') }}
        <el-select v-model="filter.folder" :aria-label="uiText('个人目录')" :disabled="loading || failed || busy" @change="applyFilter">
          <el-option :label="uiText('全部目录')" value="" />
          <el-option :label="uiText('未分类')" value="unfiled" />
          <el-option v-for="folder in folderOptions" :key="folder.id" :label="folder.path" :value="folder.id" />
        </el-select>
      </label>
      <label>{{ uiText('个人标签') }}
        <el-select v-model="filter.tag" clearable filterable allow-create default-first-option :aria-label="uiText('个人标签')" :disabled="loading || failed || busy" @change="applyFilter">
          <el-option v-for="tag in library.tags" :key="tag" :label="tag" :value="tag" />
        </el-select>
      </label>
      <label>{{ uiText('文件关键词') }}
        <el-input v-model="filter.search" maxlength="200" clearable :aria-label="uiText('文件关键词')" />
      </label>
      <el-button native-type="submit">{{ uiText('查询文件') }}</el-button>
      <el-button :disabled="loading || failed || busy" @click="openFolder(null)">{{ uiText('新建目录') }}</el-button>
      <el-button :disabled="loading || failed || busy" @click="managing = true">{{ uiText('管理目录') }}</el-button>
    </form>
    <p v-if="library.tags_truncated" class="library-hint">{{ uiText('标签候选只显示前100项，仍可输入完整标签筛选。') }}</p>
    <el-dialog v-model="managing" :title="uiText('管理目录')" width="min(560px, 94vw)" destroy-on-close :close-on-click-modal="false" :before-close="closeManager">
      <p v-if="writeError" role="alert">{{ writeError }}</p>
      <p>{{ uiText('删除目录仅移除分类，不删除文件；有子目录时须先处理子目录。') }}</p>
      <div v-for="folder in folderOptions" :key="folder.id" class="folder-row">
        <span>{{ folder.path }}</span>
        <el-button :disabled="busy" @click="openFolder(folder)">{{ uiText('编辑') }}</el-button>
        <el-button type="danger" :disabled="busy" @click="removeFolder(folder)">{{ uiText('删除') }}</el-button>
      </div>
      <el-empty v-if="!folderOptions.length" :description="uiText('暂无数据')" />
    </el-dialog>
    <el-dialog :model-value="folderDraft !== null" :title="uiText(folderDraft?.id ? '编辑目录' : '新建目录')" width="min(480px, 94vw)" :close-on-click-modal="false" :before-close="closeFolder">
      <el-form v-if="folderDraft" label-position="top" @submit.prevent="saveFolder">
        <p v-if="writeError" role="alert">{{ writeError }}</p>
        <el-form-item :label="uiText('目录名称')"><el-input v-model="folderDraft.name" maxlength="80" :aria-label="uiText('目录名称')" :disabled="busy" /></el-form-item>
        <el-form-item :label="uiText('上级目录')">
          <el-select v-model="folderDraft.parent" :aria-label="uiText('上级目录')" :disabled="busy">
            <el-option :value="''" :label="uiText('根目录')" />
            <el-option v-for="folder in availableParents" :key="folder.id" :value="folder.id" :label="folder.path" />
          </el-select>
        </el-form-item>
        <el-button native-type="submit" type="primary" :loading="busy" :disabled="!folderDraft.name.trim()">{{ uiText('保存') }}</el-button>
        <el-button :disabled="busy" @click="folderDraft = null">{{ uiText('取消') }}</el-button>
      </el-form>
    </el-dialog>
    <el-dialog :model-value="file !== null" :title="uiText('整理文件')" width="min(480px, 94vw)" :close-on-click-modal="false" :before-close="closeFile">
      <el-form v-if="file" label-position="top" @submit.prevent="saveOrganization">
        <p v-if="writeError" role="alert">{{ writeError }}</p>
        <p class="file-title">{{ file.original_name }}</p>
        <el-form-item :label="uiText('个人目录')">
          <el-select v-model="draft.folder" :aria-label="uiText('个人目录')" :disabled="busy || loading || failed">
            <el-option value="" :label="uiText('未分类')" />
            <el-option v-for="folder in folderOptions" :key="folder.id" :label="folder.path" :value="folder.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="uiText('标签（最多10个，每个32字）')">
          <el-select v-model="draft.tags" multiple filterable allow-create default-first-option :multiple-limit="10" :placeholder="uiText('选择或输入标签')" :aria-label="uiText('个人标签')" :disabled="busy || loading || failed">
            <el-option v-for="tag in library.tags" :key="tag" :label="tag" :value="tag" />
          </el-select>
        </el-form-item>
        <el-button native-type="submit" type="primary" :loading="busy" :disabled="loading || failed">{{ uiText('保存') }}</el-button>
        <el-button :disabled="busy" @click="emit('close')">{{ uiText('取消') }}</el-button>
      </el-form>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { sessionIdentity } from '@/auth/sessionIdentity'
import './libraryMessages'
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { uiText } from '@/i18n/uiText'
import { useAuthStore } from '@/stores/auth'
import { useTenantStore } from '@/stores/tenants'
import { useModuleStore } from '@/stores/modules'
import { errorMessage, responseStatus } from '@/api/request'
import { fileLibraryApi, type FileFolder, type FileLibrary, type FileLibraryFilter } from '@/api/fileLibrary'
import type { FileRow } from '@/api'

const props = defineProps<{ file: FileRow | null }>()
const emit = defineEmits<{ filter: [FileLibraryFilter]; updated: []; close: [] }>()
const auth = useAuthStore(), tenants = useTenantStore(), modules = useModuleStore()
const library = ref<FileLibrary>({ folders: [], tags: [], tags_truncated: false })
const loading = ref(false), failed = ref(false), busy = ref(false), managing = ref(false)
const writeError = ref('')
const filter = reactive<FileLibraryFilter>({ folder: '', tag: '', search: '' })
const folderDraft = ref<(Omit<FileFolder, 'parent'> & { parent: string }) | null>(null)
const draft = reactive({ version: 0, folder: '', tags: [] as string[] })
let generation = 0, scopeGeneration = 0, active = true, controller: AbortController | null = null
const identity = () => JSON.stringify([auth.user?.id, sessionIdentity(auth.token), auth.user?.permissions, auth.user?.must_change_password, tenants.currentId, modules.config])
const current = () => { const owner = identity(), epoch = scopeGeneration; return () => active && epoch === scopeGeneration && identity() === owner }
const folderOptions = computed(() => library.value.folders.map(folder => {
  const names = [folder.name], seen = new Set([folder.id]); let parent = folder.parent
  while (parent && !seen.has(parent)) {
    seen.add(parent); const row = library.value.folders.find(item => item.id === parent)
    if (!row) break
    names.unshift(row.name); parent = row.parent
  }
  return { ...folder, path: names.join(' / ') }
}).sort((a, b) => a.path.localeCompare(b.path)))
const availableParents = computed(() => folderOptions.value.filter(folder => {
  let row: FileFolder | undefined = folder
  while (row) { if (row.id === folderDraft.value?.id) return false; row = library.value.folders.find(item => item.id === row?.parent) }
  return true
}))
function applyFilter() { emit('filter', { ...filter }) }
async function load() {
  const valid = current(), tick = ++generation
  controller?.abort(); controller = new AbortController(); loading.value = true; failed.value = false
  try {
    const data = await fileLibraryApi.load(controller.signal)
    if (!valid() || tick !== generation) return
    library.value = data
    if (filter.folder && filter.folder !== 'unfiled' && !data.folders.some(item => item.id === filter.folder)) { filter.folder = ''; applyFilter() }
  } catch { if (valid() && tick === generation) failed.value = true }
  finally { if (valid() && tick === generation) loading.value = false }
}
function openFolder(row: FileFolder | null) {
  writeError.value = ''
  folderDraft.value = row ? { ...row, parent: row.parent || '' } : { id: '', name: '', parent: filter.folder === 'unfiled' ? '' : filter.folder, version: 0 }
}
async function changed(valid: () => boolean) { if (valid()) { await load(); if (valid()) emit('updated') } }
async function conflict(error: unknown, valid: () => boolean) {
  if (valid()) writeError.value = errorMessage(error, uiText('保存失败，输入已保留，请检查后重试'))
  if (valid() && responseStatus(error) === 409) {
    ElMessage.warning(uiText('目录或整理信息已变更，请刷新后重新编辑。'))
    folderDraft.value = null; emit('close'); await changed(valid)
  }
}
async function saveFolder() {
  if (!folderDraft.value || busy.value) return
  const valid = current(), row = { ...folderDraft.value }; busy.value = true; writeError.value = ''
  try {
    if (row.id) await fileLibraryApi.saveFolder({ ...row, parent: row.parent || null }, row.name.trim(), row.parent || null)
    else await fileLibraryApi.createFolder(row.name.trim(), row.parent || null)
    if (valid()) { folderDraft.value = null; ElMessage.success(uiText('目录已更新')); await changed(valid) }
  } catch (error) { await conflict(error, valid) }
  finally { if (valid()) busy.value = false }
}
async function removeFolder(row: FileFolder) {
  if (busy.value) return
  const valid = current(); writeError.value = ''
  try { await ElMessageBox.confirm(uiText('删除目录仅移除分类，不删除文件；有子目录时须先处理子目录。'), uiText('提示'), { type: 'warning' }) } catch { return }
  if (!valid()) return
  busy.value = true
  try { await fileLibraryApi.deleteFolder(row); if (valid()) { ElMessage.success(uiText('目录已删除，文件保留并归入未分类')); await changed(valid) } }
  catch (error) { await conflict(error, valid) }
  finally { if (valid()) busy.value = false }
}
async function saveOrganization() {
  if (!props.file || busy.value) return
  const valid = current(), id = props.file.id; busy.value = true; writeError.value = ''
  try {
    await fileLibraryApi.organize(id, { version: draft.version, folder: draft.folder || null, tags: [...draft.tags] })
    if (valid()) { emit('close'); ElMessage.success(uiText('整理已保存')); await changed(valid) }
  } catch (error) { await conflict(error, valid) }
  finally { if (valid()) busy.value = false }
}
function closeFolder(done: () => void) { if (!busy.value) { folderDraft.value = null; done() } }
function closeManager(done: () => void) { if (!busy.value) done() }
function closeFile(done: () => void) { if (!busy.value) { emit('close'); done() } }
watch(() => props.file, row => {
  writeError.value = ''
  draft.version = row?.organization?.version || 0; draft.folder = row?.organization?.folder || ''; draft.tags = [...(row?.organization?.tags || [])]
}, { immediate: true })
watch(identity, () => {
  scopeGeneration++; generation++; controller?.abort(); library.value = { folders: [], tags: [], tags_truncated: false }
  folderDraft.value = null; managing.value = false; busy.value = false; writeError.value = ''; emit('close')
  Object.assign(filter, { folder: '', tag: '', search: '' }); applyFilter()
  if (auth.user && modules.enabled('files')) void load()
}, { flush: 'sync', immediate: true })
onBeforeUnmount(() => { active = false; generation++; controller?.abort() })
</script>

<style scoped>
.file-library { margin-bottom: var(--spacing-md); min-width: 0; }
.library-hint { color: var(--text-secondary); font-size: 13px; margin: var(--spacing-sm) 0; }
.library-controls { display: flex; flex-wrap: wrap; align-items: flex-end; gap: var(--spacing-sm); }
.library-controls label { display: flex; flex-direction: column; gap: 4px; flex: 1 1 180px; min-width: 0; }
.library-controls .el-select, .el-form .el-select { width: 100%; }
.library-controls .el-button { margin-left: 0; min-height: 36px; }
.folder-row { display: flex; align-items: center; gap: var(--spacing-sm); padding-block: var(--spacing-sm); }
.folder-row span { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.folder-row .el-button { margin-left: 0; }
.file-title { overflow-wrap: anywhere; }
@media (max-width: 480px) { .library-controls label { flex-basis: 100%; } .library-controls .el-button { min-height: 44px; } }
</style>
