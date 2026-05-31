import { createApiQuery, postApi } from '../lib/api'
import { WeeklyReviewSchema } from '../lib/schemas'
import type { z } from 'zod'

export type WeeklyReview = z.infer<typeof WeeklyReviewSchema>

const useWeeklyReviewQuery = createApiQuery<WeeklyReview>('/weekly-review.json', WeeklyReviewSchema)

export function useWeeklyReview() {
  return useWeeklyReviewQuery({ refetchInterval: 120_000, staleTime: 60_000 })
}

export async function acknowledgeWeeklyReview(): Promise<void> {
  await postApi('/weekly-review/acknowledge')
}
