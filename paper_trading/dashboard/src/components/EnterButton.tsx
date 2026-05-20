interface Props {
  onClick: () => void
}

export default function EnterButton({ onClick }: Props) {
  return (
    <section className="bg-gray-950 px-6 pb-32">
      <div className="max-w-6xl mx-auto flex justify-center">
        <button
          onClick={onClick}
          className="group relative px-10 py-3.5 rounded-xl text-white font-semibold text-sm transition-all duration-300 overflow-hidden"
        >
          <span className="absolute inset-0 rounded-xl bg-gradient-to-r from-emerald-600 to-emerald-500 opacity-90 group-hover:opacity-100 transition-opacity" />
          <span className="absolute inset-0 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-400 opacity-0 group-hover:opacity-100 blur-xl transition-opacity" />
          <span className="absolute inset-0 rounded-xl ring-1 ring-inset ring-white/10 group-hover:ring-white/20 transition-colors" />
          <span className="relative z-10 flex items-center gap-2.5">
            Enter Dashboard
            <svg className="w-4 h-4 transition-transform duration-300 group-hover:translate-x-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" />
            </svg>
          </span>
        </button>
      </div>
    </section>
  )
}
