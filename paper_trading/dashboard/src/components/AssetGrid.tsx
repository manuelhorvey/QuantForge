import { useMemo } from 'react'
import { usePortfolioState } from '../hooks/usePortfolioState'
import AssetCard from './AssetCard'
import SatelliteCard from './SatelliteCard'
import Panel from './ui/Panel'
import SectionHeader from './ui/SectionHeader'
import EmptyState from './ui/EmptyState'
import { Skeleton } from './ui/Skeleton'

export default function AssetGrid() {
  const { data, isPending } = usePortfolioState()
  const sat = data?.engine_status?.satellite
  const assetNames = useMemo(() => {
    if (!data?.assets) return []
    const names = Object.keys(data.assets).sort()
    return sat ? names.filter(n => n !== "BTC") : names
  }, [data, sat])

  if (isPending) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-28 rounded-lg" />
        ))}
      </div>
    )
  }

  if (assetNames.length === 0 && !sat) {
    return (
      <Panel className="p-4">
        <SectionHeader title="Assets" accent="neutral" />
        <EmptyState message="No assets available yet" compact />
      </Panel>
    )
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
      {assetNames.map(name => (
        <AssetCard key={name} name={name} />
      ))}
      {sat && <SatelliteCard />}
    </div>
  )
}
