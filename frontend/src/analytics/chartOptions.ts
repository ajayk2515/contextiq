import type { EChartsOption } from 'echarts'

import type { EvaluationHistoryItem, LatencyPoint, StrategyDistributionItem } from '@/api/analytics'
import { formatStrategyLabel } from '@/utils/labels'

const axis = {
  axisLine: { lineStyle: { color: '#d9e0e3' } },
  axisLabel: { color: '#627078', fontSize: 11 },
  splitLine: { lineStyle: { color: '#edf1f2' } },
}
const strategyColors = ['#0b6b57', '#376b9b', '#b26a24', '#7b5b91'] as const

function shortTimestamp(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value))
}

export function strategyChartOption(items: StrategyDistributionItem[]): EChartsOption {
  return {
    animation: false,
    color: [...strategyColors],
    grid: { left: 8, right: 18, top: 12, bottom: 8, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { ...axis, type: 'value', minInterval: 1 },
    yAxis: {
      ...axis,
      type: 'category',
      data: items.map((item) => formatStrategyLabel(item.strategy)),
      axisTick: { show: false },
    },
    series: [
      {
        name: 'Queries',
        type: 'bar',
        barMaxWidth: 30,
        data: items.map((item, index) => ({
          value: item.count,
          itemStyle: { color: strategyColors[index % strategyColors.length] ?? strategyColors[0] },
        })),
      },
    ],
  }
}

export function evaluationChartOption(items: EvaluationHistoryItem[]): EChartsOption {
  const labels = items.map((item) => shortTimestamp(item.completed_at))
  return {
    animation: false,
    color: ['#0b6b57', '#376b9b', '#b26a24', '#7b5b91'],
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0, textStyle: { color: '#627078', fontSize: 11 } },
    grid: { left: 8, right: 18, top: 12, bottom: 54, containLabel: true },
    xAxis: { ...axis, type: 'category', boundaryGap: false, data: labels },
    yAxis: { ...axis, type: 'value', min: 0, max: 1 },
    series: [
      {
        name: 'Faithfulness',
        type: 'line',
        connectNulls: false,
        data: items.map((x) => x.faithfulness),
      },
      {
        name: 'Answer relevancy',
        type: 'line',
        connectNulls: false,
        data: items.map((x) => x.answer_relevancy),
      },
      {
        name: 'Context precision',
        type: 'line',
        connectNulls: false,
        data: items.map((x) => x.context_precision),
      },
      {
        name: 'Context recall',
        type: 'line',
        connectNulls: false,
        data: items.map((x) => x.context_recall),
      },
    ],
  }
}

export function latencyChartOption(items: LatencyPoint[]): EChartsOption {
  return {
    animation: false,
    color: ['#376b9b'],
    tooltip: { trigger: 'axis', valueFormatter: (value) => `${String(value)} ms` },
    grid: { left: 8, right: 18, top: 12, bottom: 8, containLabel: true },
    xAxis: {
      ...axis,
      type: 'category',
      boundaryGap: false,
      data: items.map((item) => shortTimestamp(item.timestamp)),
      axisLabel: { color: '#627078', fontSize: 11, hideOverlap: true },
    },
    yAxis: { ...axis, type: 'value', name: 'ms', nameTextStyle: { color: '#627078' } },
    series: [
      {
        name: 'Retrieval latency',
        type: 'line',
        showSymbol: items.length < 20,
        data: items.map((item) => item.retrieval_latency_ms),
      },
    ],
  }
}
