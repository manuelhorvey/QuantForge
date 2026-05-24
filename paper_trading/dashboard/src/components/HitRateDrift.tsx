import { useMemo } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from 'recharts'
import { usePortfolioState } from '../hooks/usePortfolioState'
import ChartContainer from './ui/ChartContainer'
import {
  axisTick,
  cartesianGridProps,
  chartMargin,
  tooltipLabelStyle,
  tooltipStyle,
} from './ui/chartTheme'

interface HitRateData {
  asset: string
  tp_rate: number
  sl_rate: number
  n_trades: number
}

export default function HitRateDrift() {
  const { data, isPending } = usePortfolioState()

  const chartData: HitRateData[] = useMemo(() => {
    if (!data?.assets) return []
    return Object.entries(data.assets)
      .map(([name, asset]) => {
        const er = asset.metrics?.exit_reasons
        if (!er || er.tp_rate == null) return null
        return {
          asset: name,
          tp_rate: er.tp_rate,
          sl_rate: er.sl_rate,
          n_trades: asset.metrics?.n_trades ?? 0,
        }
      })
      .filter((d): d is HitRateData => d !== null && d.n_trades > 0)
      .sort((a, b) => b.n_trades - a.n_trades)
  }, [data])

  const isEmpty = chartData.length === 0

  return (
    <ChartContainer
      title="SL/TP Hit Rate"
      accent="purple"
      meta={
        <span className="text-2xs text-tertiary font-mono tabular-nums">
          {chartData.length} assets
        </span>
      }
      isPending={isPending}
      isEmpty={isEmpty}
      emptyMessage="No trade data yet"
      height="h-48 sm:h-56"
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={chartData}
          margin={chartMargin}
          layout="vertical"
          barCategoryGap="20%"
          barGap={2}
        >
          <CartesianGrid {...cartesianGridProps} horizontal={false} />
          <XAxis
            type="number"
            domain={[0, 1]}
            tickFormatter={v => `${(v * 100).toFixed(0)}%`}
            tick={axisTick}
            axisLine={{ stroke: 'var(--color-border)' }}
            tickLine={false}
          />
          <YAxis
            type="category"
            dataKey="asset"
            tick={axisTick}
            axisLine={false}
            tickLine={false}
            width={60}
          />
          <Tooltip
            contentStyle={tooltipStyle}
            labelStyle={tooltipLabelStyle}
            formatter={(value: number) => `${(value * 100).toFixed(1)}%`}
          />
          <Legend
            wrapperStyle={{ fontSize: 10, fontFamily: 'var(--font-mono)' }}
            iconSize={8}
          />
          <Bar
            dataKey="tp_rate"
            name="TP"
            fill="var(--color-gov-green)"
            fillOpacity={0.85}
            barSize={8}
            radius={[2, 2, 0, 0]}
          />
          <Bar
            dataKey="sl_rate"
            name="SL"
            fill="var(--color-gov-red)"
            fillOpacity={0.85}
            barSize={8}
            radius={[2, 2, 0, 0]}
          />
        </BarChart>
      </ResponsiveContainer>
    </ChartContainer>
  )
}
