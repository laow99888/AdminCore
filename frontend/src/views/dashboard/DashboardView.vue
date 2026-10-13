<template>
  <AppLayout>
    <div class="dashboard-container">
      <div class="dashboard-header">
        <p class="page-subtitle">
          {{ greeting }}，{{ authStore.user?.username || 'Admin' }}{{ uiText("— 欢迎回到 AdminCore 管理系统") }}</p>
      </div>

      <div class="dashboard-content">
        <!-- 统计卡片 -->
        <el-row :gutter="16">
          <el-col v-for="card in statCards" :key="card.label" :xs="12" :sm="12" :md="8" :lg="4">
            <div class="stat-wrapper">
              <el-card shadow="never" class="stat-el-card">
                <div class="stat-value">{{ card.value }}</div>
                <div class="stat-label">{{ card.label }}</div>
              </el-card>
            </div>
          </el-col>
        </el-row>

        <!-- 图表区 -->
        <el-row :gutter="16">
          <el-col :xs="24" :lg="14">
            <el-card shadow="never" class="chart-card">
              <template #header>
                <div class="card-header-title">{{ uiText("近 7 日登录趋势") }}</div>
              </template>
              <BaseChart v-if="trendOption" :option="trendOption" :height="320" />
              <el-skeleton v-else :rows="5" animated />
            </el-card>
          </el-col>
          <el-col v-if="modules.enabled('tasks')" :xs="24" :lg="10">
            <el-card shadow="never" class="chart-card">
              <template #header>
                <div class="card-header-title">{{ uiText("任务状态分布") }}</div>
              </template>
              <BaseChart v-if="taskOption" :option="taskOption" :height="320" />
              <div v-else class="chart-empty">{{ uiText("暂无任务数据") }}</div>
            </el-card>
          </el-col>
        </el-row>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { uiText } from "@/i18n/uiText"

import { computed, onMounted, ref } from 'vue'
import type { EChartsOption } from 'echarts'
import { AppLayout } from '@/components'
import BaseChart from '@/components/common/BaseChart.vue'
import { dashboardApi, type DashboardStats } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import { useModuleStore } from '@/stores/modules'

const authStore = useAuthStore()
const themeStore = useThemeStore()
const modules = useModuleStore()
const stats = ref<DashboardStats | null>(null)

const greeting = computed(() => {
  const hour = new Date().getHours()
  if (hour < 6) return uiText("凌晨好")
  if (hour < 12) return uiText("上午好")
  if (hour < 18) return uiText("下午好")
  return uiText("晚上好")
})

const statCards = computed(() => {
  const totals = stats.value?.totals
  return [
    { label: uiText("活跃用户"), value: totals?.users ?? '—' },
    ...(modules.enabled('files') ? [{ label: uiText("文件总数"), value: totals?.files ?? '—' }] : []),
    ...(modules.enabled('approvals') ? [{ label: uiText("我的待审批"), value: totals?.pending_approvals ?? '—' }] : []),
    ...(modules.enabled('notifications') ? [{ label: uiText("未读通知"), value: totals?.unread_notifications ?? '—' }] : []),
    { label: uiText("今日登录"), value: totals?.today_logins ?? '—' },
    { label: uiText("今日操作"), value: totals?.today_operations ?? '—' },
  ]
})

// 主题感知的图表配色
const axisColor = computed(() => (themeStore.isDark ? '#94a3b8' : '#6b7280'))
const splitLineColor = computed(() => (themeStore.isDark ? '#475569' : '#e5e7eb'))

const trendOption = computed<EChartsOption | null>(() => {
  const trend = stats.value?.login_trend
  if (!trend?.length) return null
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: [uiText("成功"), uiText("失败")], top: 0, textStyle: { color: axisColor.value } },
    grid: { left: 16, right: 24, top: 44, bottom: 8, containLabel: true },
    xAxis: { type: 'category', data: trend.map((d) => d.date.slice(5)), axisLabel: { color: axisColor.value } },
    yAxis: { type: 'value', minInterval: 1, axisLabel: { color: axisColor.value }, splitLine: { lineStyle: { color: splitLineColor.value } } },
    series: [
      {
        name: uiText("成功"),
        type: 'line',
        smooth: true,
        data: trend.map((d) => d.success),
        itemStyle: { color: '#14b8a6' },
        areaStyle: { color: 'rgba(20, 184, 166, 0.12)' },
      },
      {
        name: uiText("失败"),
        type: 'line',
        smooth: true,
        data: trend.map((d) => d.failed),
        itemStyle: { color: '#ef4444' },
      },
    ],
  }
})

const TASK_STATUS_LABELS: Record<string, string> = {
  pending: uiText("等待执行"),
  running: uiText("执行中"),
  success: uiText("成功"),
  failed: uiText("失败"),
  cancelled: uiText("已取消"),
}

const taskOption = computed<EChartsOption | null>(() => {
  const taskStatus = stats.value?.task_status
  if (!taskStatus || Object.keys(taskStatus).length === 0) return null
  const palette = ['#14b8a6', '#f59e0b', '#10b981', '#ef4444', '#64748b']
  return {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, textStyle: { color: axisColor.value } },
    series: [
      {
        type: 'pie',
        radius: ['42%', '68%'],
        center: ['50%', '45%'],
        data: Object.entries(taskStatus).map(([status, count], i) => ({
          name: TASK_STATUS_LABELS[status] || status,
          value: count,
          itemStyle: { color: palette[i % palette.length] },
        })),
        label: { color: axisColor.value },
      },
    ],
  }
})

onMounted(async () => {
  // 顶栏未拉取过用户信息时补拉（登录页已存 user 的场景跳过）
  if (!authStore.user) await authStore.fetchUser()
  try {
    stats.value = await dashboardApi.stats()
  } catch {
    // 拦截器已提示，页面保持骨架屏
  }
})
</script>

<style scoped>
.dashboard-container {
  width: 100%;
}

.dashboard-header {
  margin-bottom: var(--spacing-xl);
}

.page-subtitle {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin: 0;
}

.dashboard-content {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.stat-wrapper {
  margin-bottom: var(--spacing-md);
}

.stat-el-card,
.chart-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
}

.card-header-title {
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.stat-value {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-primary-500);
  margin-bottom: var(--spacing-xs);
}

.stat-label {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.chart-empty {
  height: 320px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-tertiary);
}
</style>
