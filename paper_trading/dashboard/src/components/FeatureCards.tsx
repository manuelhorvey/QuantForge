import { useEffect, useRef, useState } from 'react'
import FeatureCard from './FeatureCard'
import RegimeMock from './mocks/RegimeMock'
import PortfolioMock from './mocks/PortfolioMock'
import WalkForwardMock from './mocks/WalkForwardMock'
import MacroHeadMock from './mocks/MacroHeadMock'
import BarrierMock from './mocks/BarrierMock'
import LiveMock from './mocks/LiveMock'

const cards = [
  { title: 'Regime Detection', label: 'Hurst + ADX + vol regime classifier', content: <RegimeMock /> },
  { title: 'Multi-Asset Portfolio', label: '5 driver clusters · zero correlation', content: <PortfolioMock /> },
  { title: 'Walk-Forward Validated', label: '6/6 windows positive · bootstrap validated', content: <WalkForwardMock /> },
  { title: 'Macro Expert Head', label: 'Protected macro signal · no feature drowning', content: <MacroHeadMock /> },
  { title: 'Triple Barrier Labels', label: 'TP · SL · timeout · aligned with execution', content: <BarrierMock /> },
  { title: 'Live Paper Trading', label: '6 assets · 5 driver clusters · live', content: <LiveMock /> },
]

export default function FeatureCards() {
  const [visible, setVisible] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true)
          observer.disconnect()
        }
      },
      { threshold: 0.1 },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  return (
    <section ref={ref} className="bg-gray-950 px-6 py-24">
      <div className="max-w-6xl mx-auto">
        <h2 className={`text-white text-2xl font-semibold text-center mb-12 transition-all duration-700 ease-out ${visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-6'}`}>
          Engineered for institutional-grade trading
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {cards.map((card, i) => (
            <div
              key={card.title}
              className={`transition-all duration-700 ease-out ${visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'}`}
              style={{ transitionDelay: `${i * 100}ms` }}
            >
              <FeatureCard title={card.title} label={card.label}>
                {card.content}
              </FeatureCard>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
