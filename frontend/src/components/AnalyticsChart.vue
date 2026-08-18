<script setup lang="ts">
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { init, use, type ECharts, type EChartsCoreOption } from 'echarts/core'
import { SVGRenderer } from 'echarts/renderers'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

use([BarChart, LineChart, GridComponent, LegendComponent, TooltipComponent, SVGRenderer])

const props = defineProps<{
  option: EChartsCoreOption
  label: string
}>()

const container = ref<HTMLElement | null>(null)
let chart: ECharts | null = null
let resizeObserver: globalThis.ResizeObserver | null = null

function resize() {
  chart?.resize()
}

onMounted(() => {
  if (!container.value) return
  chart = init(container.value, undefined, { renderer: 'svg' })
  chart.setOption(props.option)
  if (typeof globalThis.ResizeObserver !== 'undefined') {
    resizeObserver = new globalThis.ResizeObserver(resize)
    resizeObserver.observe(container.value)
  } else {
    window.addEventListener('resize', resize)
  }
})

watch(
  () => props.option,
  (option) => chart?.setOption(option, true),
  { deep: true },
)

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  window.removeEventListener('resize', resize)
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div ref="container" class="h-72 w-full" role="img" :aria-label="label"></div>
</template>
