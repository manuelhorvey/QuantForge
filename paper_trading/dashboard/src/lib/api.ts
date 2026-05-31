import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryOptions, UseMutationOptions } from '@tanstack/react-query'
import type { z } from 'zod'

export async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await fetch(endpoint, options)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json() as Promise<T>
}

export function createApiQuery<T>(
  endpoint: string,
  schema?: z.ZodType<T>,
  queryKey?: string,
) {
  const tag = queryKey ?? endpoint.replace(/^\//, '').replace(/\.json$/, '')
  const fetchFn = async (): Promise<T> => {
    const json = await fetchApi<unknown>(endpoint)
    if (schema) {
      const parsed = schema.safeParse(json)
      if (!parsed.success) {
        console.error(`[${tag}] validation failed:`, parsed.error.issues)
        throw new Error(`Invalid ${tag} data from server`)
      }
      return parsed.data
    }
    return json as T
  }
  return (queryOptions?: Partial<UseQueryOptions<T>>) =>
    useQuery<T>({
      queryKey: [tag],
      queryFn: fetchFn,
      ...queryOptions,
    })
}

export function createApiMutation<TResponse, TVariables = void>(
  endpoint: string,
  method: 'POST' | 'PUT' | 'DELETE' = 'POST',
  invalidateKeys?: string[][],
) {
  return (mutationOptions?: Partial<UseMutationOptions<TResponse, Error, TVariables>>) =>
    useMutation<TResponse, Error, TVariables>({
      mutationFn: async (variables) => {
        const res = await fetch(endpoint, {
          method,
          headers: variables !== undefined ? { 'Content-Type': 'application/json' } : undefined,
          body: variables !== undefined ? JSON.stringify(variables) : undefined,
        })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json() as Promise<TResponse>
      },
      ...mutationOptions,
    })
}

export async function postApi(endpoint: string): Promise<void> {
  const res = await fetch(endpoint, { method: 'POST' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
}
