import { describe, expect, it } from 'vitest'

import { evaluationChartOption, latencyChartOption, strategyChartOption } from './chartOptions'

describe('analytics chart mappings', () => {
  it('maps strategy labels and counts', () => {
    const option = strategyChartOption([
      { strategy: 'DENSE', count: 3 },
      { strategy: 'HYBRID_RRF_RERANK', count: 2 },
    ]) as unknown as {
      yAxis: { data: string[] }
      series: Array<{ data: Array<{ value: number }> }>
    }

    expect(option.yAxis.data).toEqual(['Dense', 'Hybrid RRF + Reranker'])
    expect(option.series[0]?.data.map((item) => item.value)).toEqual([3, 2])
  })

  it('keeps null evaluation metrics as chart gaps', () => {
    const option = evaluationChartOption([
      {
        run_id: 'run-1',
        completed_at: '2026-08-18T10:00:00Z',
        faithfulness: 0.9,
        answer_relevancy: null,
        context_precision: 0.7,
        context_recall: 0.6,
      },
    ]) as unknown as { series: Array<{ name: string; data: Array<number | null> }> }

    expect(option.series.find((series) => series.name === 'Faithfulness')?.data).toEqual([0.9])
    expect(option.series.find((series) => series.name === 'Answer relevancy')?.data).toEqual([null])
  })

  it('maps latency points in the API-provided order', () => {
    const option = latencyChartOption([
      { query_id: 'one', timestamp: '2026-08-18T10:00:00Z', retrieval_latency_ms: 410 },
      { query_id: 'two', timestamp: '2026-08-18T10:01:00Z', retrieval_latency_ms: 820 },
    ]) as unknown as { series: Array<{ data: number[] }> }

    expect(option.series[0]?.data).toEqual([410, 820])
  })
})
