import type { ExecutedRetrievalStrategy } from '@/api/chat'

export function formatIdentifierLabel(value: string) {
  return value
    .toLowerCase()
    .split('_')
    .map((word) => {
      if (word === 'rrf' || word === 'faq') return word.toUpperCase()
      if (word === 'rerank') return 'Reranker'
      return word.charAt(0).toUpperCase() + word.slice(1)
    })
    .join(' ')
}

export function formatStrategyLabel(strategy: ExecutedRetrievalStrategy) {
  if (strategy === 'HYBRID_RRF_RERANK') return 'Hybrid RRF + Reranker'
  if (strategy === 'HYBRID_RRF') return 'Hybrid RRF'
  if (strategy === 'DENSE_FALLBACK') return 'Dense fallback'
  return 'Dense'
}
