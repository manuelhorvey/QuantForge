import { useState } from 'react'
import { useEngineLogs } from '../hooks/useEngineLogs'

export default function EngineLogs() {
  const [open, setOpen] = useState(false)
  const { data, isFetching, error } = useEngineLogs()

  const lineCount = data ? data.split('\n').length : 0

  return (
    <div className="card-gradient card-border rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3 text-xs font-medium text-secondary bg-surface hover:bg-panel/50 transition-colors border-b border-default"
      >
        <div className="flex items-center gap-2">
          <svg className={`w-3.5 h-3.5 transition-transform duration-200 ${open ? 'rotate-90' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
          <span>Engine Logs</span>
          <span className="px-1.5 py-0.5 rounded text-[10px] bg-panel text-tertiary font-mono">
            {lineCount > 0 ? `${lineCount} lines` : '—'}
          </span>
        </div>
        <span className="flex items-center gap-2 text-tertiary">
          {isFetching && (
            <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          )}
          <span className="text-tertiary">{open ? 'Collapse' : 'Expand'}</span>
        </span>
      </button>
      {open && (
        <div className="max-h-72 overflow-y-auto">
          {error ? (
            <div className="px-4 py-6 text-xs text-tertiary text-center font-mono">
              [log unavailable]
            </div>
          ) : data ? (
            <pre className="px-4 py-3 text-[11px] font-mono text-secondary leading-relaxed whitespace-pre-wrap break-all">
              {data}
            </pre>
          ) : (
            <div className="px-4 py-6 flex items-center justify-center gap-2">
              <svg className="w-3.5 h-3.5 text-tertiary animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <span className="text-xs text-tertiary font-mono">Loading...</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
