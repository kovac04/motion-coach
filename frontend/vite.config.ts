import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const backend = process.env.BACKEND_URL ?? 'http://localhost:8000'

// Proxy keeps provider secrets server-side and avoids CORS during dev.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // ws: true so the /api/sensor/stream WebSocket is proxied too.
      '/api': { target: backend, ws: true },
      '/health': backend,
    },
  },
})
