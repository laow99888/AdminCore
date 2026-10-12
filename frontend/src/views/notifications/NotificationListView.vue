<template>
  <AppLayout>
    <div class="notification-container">
      <BaseCard>
        <template #header>
          <div class="card-header-row">
            <div class="card-header-title">{{ uiText("通知中心") }}</div>
            <div class="header-actions">
              <el-radio-group v-model="filterRead" @change="handleFilterChange">
                <el-radio-button value="all">{{ uiText("全部") }}</el-radio-button>
                <el-radio-button value="unread">{{ uiText("未读") }}</el-radio-button>
              </el-radio-group>
              <BaseButton variant="ghost" @click="handleMarkAll">{{ uiText("全部已读") }}</BaseButton>
            </div>
          </div>
        </template>

        <div v-loading="loading" class="notification-list">
          <div
            v-for="item in tableData"
            :key="item.id"
            class="notification-item"
            :class="{ unread: !item.is_read }"
            @click="handleRead(item)"
          >
            <div class="item-header">
              <el-tag :type="typeTag(item.notification_type)" size="small">
                {{ TYPE_LABELS[item.notification_type] || item.notification_type }}
              </el-tag>
              <span class="item-title">{{ item.title }}</span>
              <span v-if="!item.is_read" class="unread-dot"></span>
              <span class="item-time">{{ item.created_at }}</span>
            </div>
            <div v-if="item.content" class="item-content">{{ item.content }}</div>
          </div>
          <el-empty v-if="!loading && tableData.length === 0" :description="uiText('暂无通知')" />
        </div>

        <div class="pagination-row">
          <el-pagination
            background
            layout="total, prev, pager, next"
            :current-page="currentPage"
            :page-size="pageSize"
            :total="total"
            @current-change="handlePageChange"
          />
        </div>
      </BaseCard>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { uiText } from "@/i18n/uiText"

import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import AppLayout from '../../components/layout/AppLayout.vue'
import { BaseCard, BaseButton } from '@/components'
import { notificationsApi, type NotificationRow } from '@/api'

const router = useRouter()
const loading = ref(false)
const filterRead = ref<'all' | 'unread'>('all')
const tableData = ref<NotificationRow[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(10)

const TYPE_LABELS: Record<string, string> = {
  system: uiText("系统"),
  approval: uiText("审批"),
  task: uiText("任务"),
  announcement: uiText("公告"),
}

const typeTag = (type: string) =>
  ({ system: 'info', approval: 'warning', task: 'success', announcement: 'primary' }[type] || 'info')

const loadList = async () => {
  loading.value = true
  try {
    const data = await notificationsApi.list({
      page: currentPage.value,
      page_size: pageSize.value,
      ...(filterRead.value === 'unread' ? { is_read: 'False' } : {}),
    })
    tableData.value = data.items
    total.value = data.pagination.total
  } finally {
    loading.value = false
  }
}

const handleFilterChange = () => {
  currentPage.value = 1
  loadList()
}

const handleRead = async (item: NotificationRow) => {
  if (!item.is_read) {
    try {
      await notificationsApi.markRead(item.id)
      item.is_read = true
    } catch {
      // 静默
    }
  }
  if (item.link) router.push(item.link)
}

const handleMarkAll = async () => {
  await notificationsApi.markAllRead()
  ElMessage.success(uiText("已全部标记为已读"))
  loadList()
}

const handlePageChange = (page: number) => {
  currentPage.value = page
  loadList()
}

loadList()
</script>

<style scoped>
.notification-container {
  width: 100%;
}

.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-actions {
  display: flex;
  gap: var(--spacing-md);
  align-items: center;
}

.card-header-title {
  font-weight: var(--font-weight-semibold);
}

.notification-list {
  min-height: 200px;
}

.notification-item {
  padding: var(--spacing-md) var(--spacing-sm);
  border-bottom: 1px solid var(--color-border);
  cursor: pointer;
  transition: background-color var(--transition-fast);
}

.notification-item:hover {
  background-color: var(--color-bg-elevated);
}

.notification-item.unread .item-title {
  font-weight: var(--font-weight-semibold);
}

.item-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.item-title {
  color: var(--color-text-primary);
  flex: 1;
}

.unread-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: var(--color-primary-500);
  flex-shrink: 0;
}

.item-time {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  flex-shrink: 0;
}

.item-content {
  margin-top: var(--spacing-xs);
  padding-left: 2px;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pagination-row {
  display: flex;
  justify-content: flex-end;
  padding-top: var(--spacing-md);
}
</style>
