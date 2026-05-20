import { useState, useCallback } from 'react'
import App from './App'
import ErrorBoundary from './components/ErrorBoundary'
import HeroReveal from './components/HeroReveal'
import FeatureCards from './components/FeatureCards'
import EnterButton from './components/EnterButton'

export default function LandingPage() {
  const [entered, setEntered] = useState(false)

  const handleEnter = useCallback(() => {
    setEntered(true)
  }, [])

  if (entered) {
    return <ErrorBoundary><App /></ErrorBoundary>
  }

  return (
    <div className="bg-gray-950 min-h-screen">
      <HeroReveal />
      <FeatureCards />
      <EnterButton onClick={handleEnter} />
    </div>
  )
}
