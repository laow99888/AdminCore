<template>
  <div ref="chartRef" class="base-chart" :style="{ height: `${height}px` }"></div>
</template>

<script setup lang="ts">

import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { useThemeStore } from '../../stores/theme'

interface Props {
  option: echarts.EChartsOption
  height?: number
}

const props = withDefaults(defineProps<Props>(), {
  height: 320,
})

const chartRef = ref<HTMLDivElement>()
const themeStore = useThemeStore()
let chart: echarts.ECharts | null = null

const render = () => {
  if (!chartRef.value) return
  if (!chart) {
    chart = echarts.init(chartRef.value)
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
