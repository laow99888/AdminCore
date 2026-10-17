<template>
  <div ref="chartRef" class="base-chart" :style="{ height: `${height}px` }" :aria-hidden="table ? true : undefined" :role="table ? undefined : 'img'" :aria-label="table ? undefined : caption"></div>
  <details v-if="table" class="chart-data">
    <summary>{{ uiText('查看图表数据') }}</summary>
    <div class="chart-data-scroll"><table><caption>{{ caption }}</caption><thead><tr><th v-for="(column, index) in table.headers" :key="index" scope="col">{{ column }}</th></tr></thead>
      <tbody><tr v-for="(row, index) in table.rows" :key="index"><td v-for="(value, column) in row" :key="column">{{ value }}</td></tr></tbody></table></div>
  </details>
</template>

<script setup lang="ts">

import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { init, use, type ECharts, type EChartsCoreOption } from 'echarts/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useThemeStore } from '../../stores/theme'
import { uiText } from '@/i18n/uiText'

interface Props {
  option: EChartsCoreOption
  height?: number
  caption: string
  table?: { headers: string[]; rows: Array<Array<string | number>> }
}

const props = withDefaults(defineProps<Props>(), {
  height: 320,
})

const chartRef = ref<HTMLDivElement>()
use([BarChart, LineChart, PieChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])
const themeStore = useThemeStore()
let chart: ECharts | null = null

const render = () => {
  if (!chartRef.value) return
  if (!chart) {
    chart = init(chartRef.value)
  }
  chart.setOption(props.option, true)
}

const handleResize = () => chart?.resize()

onMounted(() => {
  render()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  chart?.dispose()
  chart = null
})

// 数据或主题变化时重绘
watch(() => props.option, render, { deep: true })
watch(() => themeStore.isDark, render)
</script>

<style scoped>
.base-chart {
  width: 100%;
}
.chart-data { margin-top: var(--spacing-sm); }
.chart-data summary { cursor: pointer; }
.chart-data-scroll { overflow-x: auto; }
.chart-data table { width: 100%; border-collapse: collapse; }
.chart-data th, .chart-data td { padding: var(--spacing-sm); text-align: left; border-bottom: 1px solid var(--color-border); }
</style>
