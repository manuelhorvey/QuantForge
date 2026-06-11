import { useActiveSection } from '../../hooks/useActiveSection'
import {
  LayoutDashboard,
  TrendingUp,
  Zap,
  BarChart3,
  Activity,
  Heart,
  type LucideIcon,
} from 'lucide-react'

interface NavItem {
  id: string
  label: string
  icon: LucideIcon
}

interface NavGroup {
  title: string
  items: NavItem[]
}

const NAV_GROUPS: NavGroup[] = [
  {
    title: 'Monitor',
    items: [{ id: 'monitor', label: 'System Monitor', icon: LayoutDashboard }],
  },
  {
    title: 'Portfolio',
    items: [{ id: 'portfolio', label: 'Portfolio', icon: TrendingUp }],
  },
  {
    title: 'Signals & Execution',
    items: [
      { id: 'signals', label: 'Signals', icon: Zap },
      { id: 'execution', label: 'Execution', icon: BarChart3 },
    ],
  },
  {
    title: 'Trades',
    items: [{ id: 'trades', label: 'Trades', icon: Activity }],
  },
  {
    title: 'Governance',
    items: [{ id: 'risk', label: 'System Health', icon: Heart }],
  },
]

interface SidebarProps {
  open: boolean
  onClose: () => void
}

export default function Sidebar({ open, onClose }: SidebarProps) {
  const active = useActiveSection()

  const scrollTo = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
    onClose()
  }

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside
        className={`
          fixed inset-y-0 left-0 z-50 w-[220px] bg-app border-r border-default
          transform transition-transform duration-200 ease-in-out
          lg:relative lg:inset-auto lg:z-auto lg:translate-x-0 lg:sticky lg:top-[45px] lg:h-[calc(100vh-45px)] lg:overflow-y-auto
          ${open ? 'translate-x-0' : '-translate-x-full'}
        `}
      >
        <nav className="py-4 px-3 space-y-5">
          {NAV_GROUPS.map(group => (
            <div key={group.title}>
              <p className="text-[10px] font-semibold text-tertiary uppercase tracking-widest px-2 mb-1.5">
                {group.title}
              </p>
              <div className="space-y-0.5">
                {group.items.map(item => {
                  const isActive = active === item.id
                  return (
                    <button
                      key={item.id}
                      onClick={() => scrollTo(item.id)}
                      className={`
                        w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-xs font-medium
                        transition-all duration-150
                        ${isActive
                          ? 'bg-accent-emerald/10 text-accent-emerald border border-accent-emerald/20'
                          : 'text-tertiary hover:text-secondary hover:bg-panel border border-transparent'
                        }
                      `}
                    >
                      <item.icon className="w-3.5 h-3.5 shrink-0" strokeWidth={1.5} />
                      {item.label}
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
        </nav>
      </aside>
    </>
  )
}
