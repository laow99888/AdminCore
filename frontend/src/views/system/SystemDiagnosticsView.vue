<template>
  <AppLayout>
    <div class="diagnostics">
      <div class="diagnostic-header">
        <div>
          <h1>{{ uiText(monitor ? '服务监控' : '系统信息') }}</h1>
          <p>{{ uiText('只读诊断，手动刷新；未采集的数据不代表正常。') }}</p>
        </div>
        <BaseButton :loading="loading" :disabled="loading" variant="ghost" @click="load">{{ uiText('刷新') }}</BaseButton>
      </div>
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon role="alert" />
      <BaseCard v-if="loading && !information && !resources">
        <p role="status">{{ uiText('正在采集诊断信息') }}</p>
        <el-skeleton :rows="4" animated />
      </BaseCard>
      <template v-if="information && !monitor">
        <BaseCard :title="uiText('运行环境')">
          <dl class="facts">
            <div v-for="fact in facts" :key="fact[0]"><dt>{{ uiText(fact[0]) }}</dt><dd>{{ fact[1] }}</dd></div>
          </dl>
          <p class="hint">{{ uiText('启用模块') }}: {{ information.modules.join(', ') || uiText('无') }}</p>
        </BaseCard>
        <BaseCard :title="uiText('依赖状态')">
          <p class="hint">{{ uiText('探针仅检查数据库查询和 Redis PING/版本；不代表 worker、调度器或对象存储健康。') }}</p>
          <div class="service-grid">
            <article v-for="service in information.services" :key="service.name" class="service">
              <strong>{{ serviceName(service.name) }}</strong>
              <el-tag :type="service.status === 'unavailable' ? 'danger' : service.status === 'ok' ? 'success' : 'info'">{{ statusName(service.status) }}</el-tag>
              <p>{{ uiText('版本') }}: {{ service.version || '—' }}</p>
              <p>{{ uiText('探针耗时') }}: {{ service.latency_ms === null ? '—' : `${service.latency_ms} ms` }}</p>
            </article>
          </div>
        </BaseCard>
        <BaseCard v-if="information.task_metrics" :title="uiText('任务与通知诊断')">
          <p class="hint">{{ uiText('只读快照；队列条数不等于 worker 存活。失联候选仅检查最早 1000 条活跃任务的登记策略，不自动重试；耗时取最近 1000 条有起止时间的结束任务。') }}</p>
          <el-alert v-if="information.task_metrics.status !== 'ok'" :title="uiText(information.task_metrics.status === 'disabled' ? '任务模块未启用，未采集业务队列指标。' : '部分指标未采集，请检查依赖状态后重试。')" type="warning" :closable="false" show-icon />
          <dl class="facts" data-testid="task-diagnostics">
            <div v-for="fact in taskFacts" :key="fact[0]"><dt>{{ uiText(fact[0]) }}</dt><dd>{{ fact[1] }}</dd></div>
          </dl>
        </BaseCard>
        <BaseCard :title="uiText('后端实际安装依赖')">
          <dl class="facts"><div v-for="dependency in information.dependencies" :key="dependency.name"><dt>{{ dependency.name }}</dt><dd>{{ dependency.version || uiText('未安装') }}</dd></div></dl>
        </BaseCard>
      </template>
      <template v-if="resources && monitor">
        <el-alert :title="uiText(resources.scope === 'container' ? '采集范围：后端容器。CPU 按可用核数归一化，内存按 cgroup 读取；不包含其他服务容器。' : '采集范围：后端所在主机。当前平台不支持的指标显示未采集。')" type="info" :closable="false" show-icon />
        <div class="metrics">
          <BaseCard title="CPU">
            <div class="metric-value">{{ percentage(resources.cpu.percent) }}</div>
            <p class="hint">{{ uiText('可用核数') }}: {{ resources.cpu.capacity_cores ?? '—' }}</p>
            <p class="hint">{{ uiText('采样窗口') }}: {{ resources.cpu.sample_seconds === null ? '—' : `${resources.cpu.sample_seconds} s` }}</p>
          </BaseCard>
          <BaseCard :title="uiText('内存')">
            <div class="metric-value">{{ bytes(resources.memory.used_bytes) }}</div>
            <p class="hint">{{ uiText('总量或容器上限') }}: {{ resources.memory.total_bytes === null ? uiText('未采集或未设置上限') : bytes(resources.memory.total_bytes) }}</p>
            <p class="hint">{{ uiText('使用率') }}: {{ percentage(resources.memory.percent) }}</p>
          </BaseCard>
        </div>
        <BaseCard :title="uiText('磁盘文件系统')">
          <p class="hint">{{ uiText('容量属于挂载文件系统，不是目录占用；不同用途可能共用同一磁盘。对象存储容量不在此统计。') }}</p>
          <div class="service-grid">
            <article v-for="disk in resources.disks" :key="disk.name" class="service">
              <strong>{{ diskName(disk.name) }}</strong>
              <p>{{ uiText('总量') }}: {{ bytes(disk.total_bytes) }}</p>
              <p>{{ uiText('已用') }}: {{ bytes(disk.used_bytes) }} ({{ percentage(disk.percent) }})</p>
              <p>{{ uiText('可用') }}: {{ bytes(disk.free_bytes) }}</p>
              <el-tag v-if="disk.status === 'unavailable'" type="warning">{{ uiText('未采集') }}</el-tag>
            </article>
          </div>
        </BaseCard>
        <BaseCard :title="uiText('可见进程')">
          <p class="hint">{{ uiText('最多显示 128 个可见进程；CPU 为累计秒数，RSS 不可直接相加；名称按固定类型脱敏。') }}</p>
          <el-alert v-if="resources.processes_truncated" :title="uiText('进程列表已截断')" type="warning" :closable="false" />
          <el-empty v-if="!resources.processes_supported" :description="uiText('当前平台不支持进程采集')" />
          <el-empty v-else-if="!resources.processes.length" :description="uiText('暂无可见进程')" />
          <div v-else class="process-grid">
            <article v-for="process in resources.processes" :key="process.pid" class="service">
              <strong>PID {{ process.pid }} · {{ process.kind === 'python' ? 'Python' : uiText('其他进程') }}</strong>
              <dl><div><dt>{{ uiText('状态') }}</dt><dd>{{ process.state }}</dd></div><div><dt>CPU</dt><dd>{{ process.cpu_seconds }} s</dd></div><div><dt>RSS</dt><dd>{{ bytes(process.rss_bytes) }}</dd></div><div><dt>{{ uiText('运行时长') }}</dt><dd>{{ process.uptime_seconds }} s</dd></div></dl>
            </article>
          </div>
        </BaseCard>
      </template>
      <p v-if="sampledAt" class="hint timestamp">{{ uiText('采集时间') }}: {{ sampledAt }}</p>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, version, watch } from 'vue'
import AppLayout from '@/components/layout/AppLayout.vue'
import { BaseButton, BaseCard } from '@/components'
import { diagnosticsApi, type SystemInformation, type SystemMonitor } from '@/api/diagnostics'
import { uiText } from '@/i18n/uiText'

const props = withDefaults(defineProps<{ monitor?: boolean }>(), { monitor: false })
const information = ref<SystemInformation | null>(null)
const resources = ref<SystemMonitor | null>(null)
const loading = ref(false)
const error = ref('')
let generation = 0
const sampledAt = computed(() => information.value?.sampled_at || resources.value?.sampled_at)
const facts = computed(() => information.value ? [
  ['Python', information.value.python], ['操作系统', `${information.value.os} / ${information.value.architecture}`],
  ['运行环境', information.value.environment], ['调试模式', information.value.debug ? uiText('开启') : uiText('关闭')],
  ['启用预设', information.value.preset], ['时区', information.value.timezone],
  ['数据库', information.value.database], ['存储模式', information.value.storage], ['前端 Vue 运行版本', version],
] : [])
const taskFacts = computed(() => {
  const metrics = information.value?.task_metrics
  if (!metrics) return []
  const count = (value: number | null | undefined) => value == null ? uiText('未采集') : String(value)
  const states = (value: Record<string, number> | null) => value === null ? uiText('未采集') : Object.entries(value).map(([key, total]) => `${key}: ${total}`).join(' · ') || uiText('暂无记录')
  const duration = metrics.task_records.duration_seconds
  const lost = metrics.task_records.lost_candidates
  return [
    ['代理队列待领取', metrics.broker.status === 'ok' ? count(metrics.broker.ready) : statusName(metrics.broker.status)],
    ['任务状态计数', states(metrics.task_records.counts)],
    ['失联候选（等待 / 运行）', lost ? `${lost.pending} / ${lost.running}` : uiText('未采集')],
    ['候选采样 / 未分类 / 截断', lost ? `${lost.sampled} / ${lost.unclassified} / ${uiText(lost.truncated ? '是' : '否')}` : uiText('未采集')],
    ['耗时样本 / 平均 / p95 / 最大（秒）', duration ? `${duration.count} / ${count(duration.average)} / ${count(duration.p95)} / ${count(duration.max)}` : uiText('未采集')],
    ['可靠事件状态计数', states(metrics.outbox.counts)],
    ['可靠事件最老等待 / 失败（秒）', `${count(metrics.outbox.oldest_pending_seconds)} / ${count(metrics.outbox.oldest_failed_seconds)}`],
    ['通知投递状态计数', metrics.notifications.status === 'ok' ? states(metrics.notifications.counts) : statusName(metrics.notifications.status)],
    ['通知最老等待 / 失败（秒）', `${count(metrics.notifications.oldest_pending_seconds)} / ${count(metrics.notifications.oldest_failed_seconds)}`],
    ['已关联请求的事件 / 任务 / 通知', `${count(metrics.correlation.outbox_request_linked)} / ${count(metrics.correlation.task_request_linked)} / ${count(metrics.correlation.notification_request_linked)}`],
  ]
})
function percentage(value: number | null) { return value === null ? uiText('未采集') : `${value.toFixed(2)}%` }
function bytes(value: number | null) {
  if (value === null) return uiText('未采集')
  if (value === 0) return '0 B'
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB']
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1)
  return `${(value / 1024 ** index).toFixed(index ? 2 : 0)} ${units[index]}`
}
function serviceName(name: string) { return uiText(({ database: '数据库', cache: '缓存', broker: '任务消息代理' } as Record<string, string>)[name] || name) }
function diskName(name: string) { return uiText(({ application: '应用文件系统', logs: '日志文件系统', media: '媒体文件系统' } as Record<string, string>)[name] || name) }
function statusName(status: string) { return uiText(({ ok: '正常', unavailable: '不可用', in_process: '进程内缓存', disabled: '未启用' } as Record<string, string>)[status] || status) }
async function load() {
  if (loading.value) return
  const current = ++generation
  const mode = props.monitor
  loading.value = true
  error.value = ''
  // 刷新时清除旧样本，防止旧数据被当作最新健康状态。
  information.value = null
  resources.value = null
  try {
    if (mode) {
      const result = await diagnosticsApi.monitor()
      if (current === generation) resources.value = result
    } else {
      const result = await diagnosticsApi.information()
      if (current === generation) information.value = result
    }
  } catch {
    if (current === generation) error.value = uiText('诊断信息加载失败，请刷新重试；请求过于频繁时请稍后再试。')
  } finally { if (current === generation) loading.value = false }
}
watch(() => props.monitor, () => { generation++; loading.value = false; void load() }, { immediate: true })
onBeforeUnmount(() => { generation++ })
</script>

<style scoped>
.diagnostics { display: grid; gap: var(--spacing-lg); min-width: 0; }
.diagnostic-header { display: flex; align-items: center; justify-content: space-between; gap: var(--spacing-md); }
.diagnostic-header h1 { font-size: var(--font-size-xl); margin: 0 0 var(--spacing-sm); }
.diagnostic-header p, .hint, .service p { color: var(--color-text-secondary); font-size: var(--font-size-sm); line-height: 1.6; }
.facts, .service-grid, .process-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr)); gap: var(--spacing-md); }
.facts { margin: 0; }
.facts div, .service { border: 1px solid var(--color-border); border-radius: var(--radius-md); padding: var(--spacing-md); min-width: 0; overflow-wrap: anywhere; }
dt { color: var(--color-text-secondary); font-size: var(--font-size-sm); }
dd { margin: var(--spacing-sm) 0 0; overflow-wrap: anywhere; }
.service > strong { display: block; margin-bottom: var(--spacing-sm); }
.service dl { display: grid; grid-template-columns: 1fr 1fr; gap: var(--spacing-sm); margin-bottom: 0; }
.metrics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--spacing-md); }
.metric-value { font-size: var(--font-size-2xl); font-weight: var(--font-weight-semibold); overflow-wrap: anywhere; }
.timestamp { overflow-wrap: anywhere; margin: 0; }
@media (max-width: 600px) { .metrics { grid-template-columns: 1fr; } .diagnostic-header { align-items: flex-start; } .diagnostic-header > div { min-width: 0; } }
</style>
