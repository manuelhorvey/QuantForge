import { useQueryClient } from '@tanstack/react-query'
import { createApiQuery, postApi } from '../lib/api'
import { NarrativeStatusSchema } from '../lib/schemas'
import type { z } from 'zod'

export type NarrativeStatus = z.infer<typeof NarrativeStatusSchema>

const useNarrativeQuery = createApiQuery<NarrativeStatus>('/narrative.json', NarrativeStatusSchema)

export function useNarrative() {
  return useNarrativeQuery({ refetchInterval: 300_000, staleTime: 300_000, gcTime: 600_000 })
}

export function useConfirmNarrative() {
  const queryClient = useQueryClient()
  return async () => {
    await postApi('/narrative/confirm')
    await queryClient.invalidateQueries({ queryKey: ['narrative'] })
    await queryClient.invalidateQueries({ queryKey: ['governance'] })
  }
}
