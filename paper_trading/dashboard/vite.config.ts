import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    port: 3000,
    proxy: {
      '/state.json': 'http://localhost:5000',
      '/trades.json': 'http://localhost:5000',
      '/equity_history.json': 'http://localhost:5000',
      '/confidence.json': 'http://localhost:5000',
      '/volatility.json': 'http://localhost:5000',
      '/logs': 'http://localhost:5000',
      '/risk.json': 'http://localhost:5000',
      '/health.json': 'http://localhost:5000',
      '/shadow-actions': 'http://localhost:5000',
    },
  },
})
