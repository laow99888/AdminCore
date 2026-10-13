<template>
  <div ref="chartRef" class="base-chart" :style="{ height: `${height}px` }"></div>
</template>

<script setup lang="ts">

import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { init, use, type ECharts, type EChartsCoreOption } from 'echarts/core'
import { LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useThemeStore } from '../../stores/theme'

interface Props {
  option: EChartsCoreOption
  height?: number
}

const props = withDefaults(defineProps<Props>(), {
  height: 320,
})

const chartRef = ref<HTMLDivElement>()
use([LineChart, PieChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])
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
</style>
