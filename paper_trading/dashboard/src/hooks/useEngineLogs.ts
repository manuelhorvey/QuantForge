import { useQuery } from '@tanstack/react-query'

async function fetchLogs(): Promise<string> {
  const res = await fetch('/logs')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.text()
}

export function useEngineLogs() {
  return useQuery({
    queryKey: ['engineLogs'],
    queryFn: fetchLogs,
    refetchInterval: 15_000,
    staleTime: 10_000,
  })
}
