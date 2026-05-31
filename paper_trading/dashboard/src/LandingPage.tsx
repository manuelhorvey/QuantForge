import { lazy, Suspense } from 'react'
import { useNavigate } from 'react-router-dom'
import HeroReveal from './components/HeroReveal'
import EnterButton from './components/EnterButton'

const FeatureCards = lazy(() => import('./components/FeatureCards'))

export default function LandingPage() {
  const navigate = useNavigate()

  return (
    <div className="bg-gray-950 min-h-screen">
      <HeroReveal />
      <Suspense fallback={null}>
        <FeatureCards />
      </Suspense>
      <EnterButton onClick={() => navigate('/dashboard')} />
    </div>
  )
}
