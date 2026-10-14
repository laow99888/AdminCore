<template>
  <AppLayout>
    <div class="log-container">
      <BaseCard>
        <template #header>
          <div class="card-header-row">
            <div class="card-header-title">{{ uiText("系统日志") }}</div>
            <div class="header-actions">
              <DataExportButton :loading="loading || !exportReady" resource="logs" :filters="{ ...exportFilters, log_type: activeTab }" />
              <LocalExportButton resource="logs" :title="uiText('系统日志')" :rows="printRows" :columns="printColumns" :loading="loading || !exportReady" :current-page="currentPage" :owner-key="printOwner" />
              <PrintTableButton :title="uiText('系统日志')" :rows="printRows" :columns="printColumns" :loading="loading || !exportReady" :current-page="currentPage" :allowed="auth.can('log:read')" :owner-key="printOwner" />
              <el-input
                v-model="search"
                :placeholder="uiText('搜索描述 / 用户名')"
                clearable
                style="width: 220px"
                @keyup.enter="handleSearch"
              />
              <BaseButton variant="primary" @click="handleSearch">{{ uiText("搜索") }}</BaseButton>
            </div>
          </div>
        </template>

        <el-tabs v-model="activeTab" @tab-change="handleTabChange">
          <el-tab-pane :label="uiText('操作日志')" name="operation" />
          <el-tab-pane :label="uiText('登录日志')" name="login" />
          <el-tab-pane :label="uiText('异常日志')" name="exception" />
        </el-tabs>

        <BaseTable
          v-if="activeTab === 'operation'"
          :data="operationLogs"
          :columns="operationColumns"
          :loading="loading"
          :total="total"
          :current-page="currentPage"
          :page-size="pageSize"
          :show-actions="true"
          @update:currentPage="handlePageChange"
          @update:pageSize="handlePageSizeChange"
        >
          <template #actions="{ row }"><el-button link type="primary" @click="openAudit(row.id)">{{ uiText('审计详情') }}</el-button></template>
        </BaseTable>

        <BaseTable
          v-else-if="activeTab === 'login'"
          :data="loginLogs"
          :columns="loginColumns"
          :loading="loading"
          :total="total"
          :current-page="currentPage"
          :page-size="pageSize"
          :show-actions="false"
          @update:currentPage="handlePageChange"
          @update:pageSize="handlePageSizeChange"
        />

        <BaseTable
          v-else
          :data="exceptionLogs"
          :columns="exceptionColumns"
          :loading="loading"
          :total="total"
          :current-page="currentPage"
          :page-size="pageSize"
          :show-actions="false"
          @update:currentPage="handlePageChange"
          @update:pageSize="handlePageSizeChange"
        />
      </BaseCard>
      <el-dialog :model-value="auditOpen" :title="uiText('审计详情')" :width="isMobile ? 'calc(100vw - 24px)' : '680px'" @close="closeAudit">
        <el-skeleton v-if="auditLoading" :rows="5" animated />
        <div v-else-if="auditError" role="alert"><p>{{ uiText('审计详情加载失败，请重试') }}</p><el-button @click="openAudit(auditId)">{{ uiText('重试') }}</el-button></div>
        <div v-else-if="auditRow" class="audit-details">
          <dl><dt>{{ uiText('操作者标识') }}</dt><dd>{{ auditRow.actor_identifier || uiText('未记录') }}</dd><dt>{{ uiText('请求关联 ID') }}</dt><dd>{{ auditRow.request_id || uiText('未记录') }}</dd><dt>{{ uiText('任务关联 ID') }}</dt><dd>{{ auditRow.task_record_id || auditRow.task_id || uiText('未记录') }}</dd></dl>
          <el-alert v-if="!auditRow.audit_version" :title="uiText('此记录未登记结构化前后值，以下内容为原日志描述。')" type="info" :closable="false" />
          <template v-else><h3>{{ uiText('变更前') }}</h3><pre>{{ JSON.stringify(auditRow.before_values, null, 2) }}</pre><h3>{{ uiText('变更后') }}</h3><pre>{{ JSON.stringify(auditRow.after_values, null, 2) }}</pre><h3 v-if="auditRow.batch_results?.length">{{ uiText('逐项结果') }}</h3><pre v-if="auditRow.batch_results?.length">{{ JSON.stringify(auditRow.batch_results, null, 2) }}</pre></template>
          <p>{{ auditRow.description }}</p>
        </div>
      </el-dialog>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { uiText } from "@/i18n/uiText"

import { computed, ref, watch, onMounted, onActivated, onDeactivated, onBeforeUnmount } from 'vue'
import AppLayout from '../../components/layout/AppLayout.vue'
import { BaseCard, BaseButton, BaseTable } from '@/components'
import { logsApi, type OperationLogRow } from '@/api'
import { usePageState } from '@/composables/usePageState'
import DataExportButton from '@/components/common/DataExportButton.vue'
import PrintTableButton from '@/components/common/PrintTableButton.vue'
import LocalExportButton from '@/components/common/LocalExportButton.vue'
import type { PrintColumn } from '@/utils/printDocument'
import { useAuthStore } from '@/stores/auth'
import { useSidebar } from '@/composables/useSidebar'

defineOptions({ name: 'OperationLogView' })

const loading = ref(false)
const activeTab = ref('operation')
const search = ref('')
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(10)
const auth = useAuthStore()
const { isMobile } = useSidebar()
const auditOpen = ref(false), auditLoading = ref(false), auditError = ref(false), auditId = ref('')
const auditRow = ref<OperationLogRow | null>(null)
let auditGeneration = 0
function closeAudit() { auditGeneration++; auditOpen.value = false; auditRow.value = null; auditId.value = ''; auditLoading.value = false; auditError.value = false }
async function openAudit(id: string) {
  if (!active || !auth.can('log:read') || !id) return
  const current = ++auditGeneration
  auditOpen.value = true; auditId.value = id; auditRow.value = null; auditLoading.value = true; auditError.value = false
  try {
    const row = await logsApi.operationDetail(id)
    if (current === auditGeneration && active && auth.can('log:read')) auditRow.value = row
  } catch { if (current === auditGeneration && active) auditError.value = true }
  finally { if (current === auditGeneration) auditLoading.value = false }
}
const exportFilters = ref<{ search?: string }>({})
const printOwner = computed(() => JSON.stringify([auth.user?.id, auth.token, auth.user?.permissions]))
watch(printOwner, () => {
  closeAudit(); generation++; loading.value = false; exportReady.value = false
  operationLogs.value = []; loginLogs.value = []; exceptionLogs.value = []; total.value = 0
  if (active && auth.can('log:read')) void loadLogs()
}, { flush: 'sync' })
usePageState({ activeTab, search, currentPage, pageSize })

const operationLogs = ref<OperationLogRow[]>([])
const loginLogs = ref<any[]>([])
const exceptionLogs = ref<any[]>([])
const printRows = computed(() => activeTab.value === 'operation' ? operationLogs.value : activeTab.value === 'login' ? loginLogs.value : exceptionLogs.value)
const printColumns = computed<PrintColumn<Record<string, any>>[]>(() => activeTab.value === 'operation' ? [
  { label: uiText('时间'), value: row => row.created_at },
  { label: uiText('操作'), value: row => row.action },
  { label: uiText('资源'), value: row => row.resource },
  { label: uiText('状态码'), value: row => row.status },
] : activeTab.value === 'login' ? [
  { label: uiText('时间'), value: row => row.created_at },
  { label: uiText('用户名'), value: row => row.username },
  { label: uiText('结果'), value: row => uiText(row.status === 'success' ? '成功' : '失败') },
] : [
  { label: uiText('时间'), value: row => row.created_at },
  { label: uiText('级别'), value: row => row.level },
])

const ACTION_LABELS: Record<string, string> = {
  create: uiText("创建"), read: uiText("查看"), update: uiText("修改"), delete: uiText("删除"),
  export: uiText("导出"), import: uiText("导入"), download: uiText("下载"), upload: uiText("上传"),
  login: uiText("登录"), logout: uiText("登出"), other: uiText("其他"),
}

const operationColumns = [
  { prop: 'created_at', label: uiText("时间"), width: '180px' },
  { prop: 'action', label: uiText("操作"), width: '90px', render: (v: string) => ACTION_LABELS[v] || v },
  { prop: 'resource', label: uiText("资源"), width: '110px' },
  { prop: 'description', label: uiText("描述") },
  { prop: 'status', label: uiText("状态码"), width: '90px' },
]

const loginColumns = [
  { prop: 'created_at', label: uiText("时间"), width: '180px' },
  { prop: 'username', label: uiText("用户名") },
  {
    prop: 'status',
    label: uiText("结果"),
    width: '90px',
    render: (v: string) => (v === 'success' ? uiText("成功") : uiText("失败")),
  },
  { prop: 'ip_address', label: 'IP', width: '140px' },
  { prop: 'error_message', label: uiText("错误信息") },
]

const exceptionColumns = [
  { prop: 'created_at', label: uiText("时间"), width: '180px' },
  { prop: 'level', label: uiText("级别"), width: '90px' },
  {
    prop: 'message',
    label: uiText("错误信息"),
    render: (v: string) => (v ? v.slice(0, 80) : ''),
  },
  { prop: 'request_path', label: uiText("请求路径") },
]

let active = true, generation = 0
const exportReady = ref(false)
const loadLogs = async () => {
  exportReady.value = false
  const current = ++generation
  const tab = activeTab.value
  loading.value = true
  const filters = search.value ? { search: search.value } : {}
  try {
    const params = {
      page: currentPage.value,
      page_size: pageSize.value,
      ...filters,
    }
    let data
    if (tab === 'operation') {
      data = await logsApi.operation(params)
      if (!active || current !== generation) return
      operationLogs.value = data.items
    } else if (tab === 'login') {
      data = await logsApi.login(params)
      if (!active || current !== generation) return
      loginLogs.value = data.items
    } else {
      data = await logsApi.exception(params)
      if (!active || current !== generation) return
      exceptionLogs.value = data.items
    }
    exportReady.value = true
    total.value = data.pagination.total
    exportFilters.value = filters
  } catch { /* 请求拦截器显示错误，保持查询条件以便重试。 */ }
  finally {
    if (active && current === generation) loading.value = false
  }
}

const handleTabChange = () => {
  closeAudit()
  currentPage.value = 1
  loadLogs()
}

const handleSearch = () => {
  currentPage.value = 1
  loadLogs()
}

const handlePageChange = (page: number) => {
  currentPage.value = page
  loadLogs()
}

const handlePageSizeChange = (size: number) => {
  pageSize.value = size
  currentPage.value = 1
  loadLogs()
}

onMounted(() => { void loadLogs() })
onActivated(() => { active = true; if (!loading.value) void loadLogs() })
onDeactivated(() => { closeAudit(); active = false; generation++; loading.value = false; exportReady.value = false; operationLogs.value = []; loginLogs.value = []; exceptionLogs.value = []; total.value = 0 })
onBeforeUnmount(() => { closeAudit(); active = false; generation++ })
</script>

<style scoped>
.log-container {
  width: 100%;
}

.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--spacing-sm);
}

.header-actions {
  display: flex;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
  max-width: 100%;
}

.header-actions :deep(.el-input) { max-width: 100%; }

.card-header-title {
  font-weight: var(--font-weight-semibold);
}
.audit-details { overflow-wrap: anywhere; }
.audit-details dd { margin: 0 0 var(--spacing-sm); }
.audit-details pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 240px; overflow: auto; background: var(--bg-secondary); padding: var(--spacing-sm); }
</style>
