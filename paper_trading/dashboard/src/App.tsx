import { usePortfolioState } from './hooks/usePortfolioState'
import Header from './components/Header'
import PortfolioSummary from './components/PortfolioSummary'
import AssetGrid from './components/AssetGrid'
import SignalsTable from './components/SignalsTable'
import MetricsGrid from './components/MetricsGrid'
import HaltConditions from './components/HaltConditions'
import TradeFeed from './components/TradeFeed'
import EquityChart from './components/EquityChart'
import ConfidenceChart from './components/ConfidenceChart'
import VolRegimePanel from './components/VolRegimePanel'
import HealthScores from './components/HealthScores'
import EngineLogs from './components/EngineLogs'
import Footer from './components/Footer'

function ConnectingScreen() {
  return (
    <div className="min-h-screen bg-gray-950 flex flex-col items-center justify-center gap-4 px-6">
      <svg className="w-8 h-8 text-emerald-500 animate-spin" fill="none" viewBox="0 0 24 24">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      <div className="text-center">
        <h2 className="text-white text-lg font-semibold">Connecting to QuantForge Engine</h2>
        <p className="text-gray-500 text-sm mt-1">Waiting for paper trading data...</p>
      </div>
      <div className="flex gap-1.5 mt-2">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500/50 animate-pulse" style={{ animationDelay: '0ms' }} />
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500/50 animate-pulse" style={{ animationDelay: '200ms' }} />
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500/50 animate-pulse" style={{ animationDelay: '400ms' }} />
      </div>
    </div>
  )
}

export default function App() {
  const { isPending, isError } = usePortfolioState()

  if (isPending) {
    return <ConnectingScreen />
  }

  if (isError) {
    return (
      <div className="min-h-screen bg-gray-950 flex flex-col items-center justify-center gap-4 px-6">
        <svg className="w-8 h-8 text-amber-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
        </svg>
        <div className="text-center">
          <h2 className="text-white text-lg font-semibold">Engine Not Reachable</h2>
          <p className="text-gray-500 text-sm mt-1">Make sure the paper trading engine is running on port 5000</p>
        </div>
        <button
          onClick={() => window.location.reload()}
          className="mt-2 px-5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium transition-colors"
        >
          Retry
        </button>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-app text-secondary">
      <div className="fixed inset-0 pointer-events-none opacity-[0.03]" style={{
        backgroundImage: 'radial-gradient(currentColor 1px, transparent 1px)',
        backgroundSize: '32px 32px',
      }} />
      <Header />

      <main className="max-w-7xl mx-auto px-6 py-6 space-y-6 relative">
        <PortfolioSummary />
        <AssetGrid />
        <HaltConditions />

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <SignalsTable />
          <EquityChart />
        </div>

        <HealthScores />

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <MetricsGrid />
          </div>
          <div className="space-y-6">
            <ConfidenceChart />
            <VolRegimePanel />
          </div>
        </div>

        <TradeFeed />

        <EngineLogs />
      </main>

      <Footer />
    </div>
  )
}
