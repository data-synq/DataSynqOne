import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// In production Caddy serves frontend and backend from one origin and strips the
// prefix with `handle_path /api/*`. The dev proxy reproduces that exactly, so dev
// runs same-origin too: no CORS, and `/agent/chat` streams SSE unbuffered.
// `.env.development` sets VITE_BACKEND_URL=/api to point the client at it.
const proxyTarget = process.env.VITE_PROXY_TARGET ?? 'http://localhost:8001'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': {
        target: proxyTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
