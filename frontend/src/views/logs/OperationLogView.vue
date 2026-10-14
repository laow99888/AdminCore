<template>
  <AppLayout>
    <div class="log-container">
      <BaseCard>
        <template #header>
          <div class="card-header-row">
            <div class="card-header-title">{{ uiText("系统日志") }}</div>
            <div class="header-actions">
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
          :show-actions="false"
          @update:currentPage="handlePageChange"
          @update:pageSize="handlePageSizeChange"
        />

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
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { uiText } from "@/i18n/uiText"

import { ref, onActivated, onDeactivated, onBeforeUnmount } from 'vue'
import AppLayout from '../../components/layout/AppLayout.vue'
import { BaseCard, BaseButton, BaseTable } from '@/components'
import { logsApi, type OperationLogRow } from '@/api'
import { usePageState } from '@/composables/usePageState'

defineOptions({ name: 'OperationLogView' })

const loading = ref(false)
const activeTab = ref('operation')
const search = ref('')
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(10)
usePageState({ activeTab, search, currentPage, pageSize })

const operationLogs = ref<OperationLogRow[]>([])
const loginLogs = ref<any[]>([])
const exceptionLogs = ref<any[]>([])

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
const loadLogs = async () => {
  const current = ++generation
  const tab = activeTab.value
  loading.value = true
  try {
    const params = {
      page: currentPage.value,
      page_size: pageSize.value,
      ...(search.value ? { search: search.value } : {}),
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
    total.value = data.pagination.total
  } catch { /* 请求拦截器显示错误，保持查询条件以便重试。 */ }
  finally {
    if (active && current === generation) loading.value = false
  }
}

const handleTabChange = () => {
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

onActivated(() => { active = true; void loadLogs() })
onDeactivated(() => { active = false; generation++; operationLogs.value = []; loginLogs.value = []; exceptionLogs.value = []; total.value = 0 })
onBeforeUnmount(() => { active = false; generation++ })
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
</style>
