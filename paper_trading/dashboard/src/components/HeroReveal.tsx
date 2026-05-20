interface Props {
  children?: React.ReactNode
}

export default function HeroReveal({ children }: Props) {
  return (
    <div className="relative w-full h-screen overflow-hidden bg-gray-950 select-none flex flex-col items-center justify-center">
      <h1 className="text-white text-[72px] font-[500] tracking-tight">
        QuantForge
      </h1>
      <p className="text-gray-400 text-xl mt-2">
        Macro-driven. Regime-aware.
      </p>

      <div className="mt-12 flex gap-3">
        {['XLF', 'BTC', 'NZDJPY', 'GC', 'EURAUD'].map((a) => (
          <span key={a} className="px-2.5 py-1 rounded-md text-[10px] font-mono font-medium bg-gray-800 text-gray-400 border border-gray-700/50">
            {a}
          </span>
        ))}
      </div>

      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage:
            'linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px)',
          backgroundSize: '40px 40px',
        }}
      />

      <div className="absolute bottom-12 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 pointer-events-none">
        <span className="text-gray-600 text-xs tracking-wider uppercase">Move cursor to explore</span>
        <svg className="w-4 h-4 text-gray-600 animate-bounce" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 14l-7 7m0 0l-7-7m7 7V3" />
        </svg>
      </div>

      {children}
    </div>
  )
}
