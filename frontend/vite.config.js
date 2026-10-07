import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The frontend calls the backend as /api/* so it never hard-codes a host.
// The dev server forwards those calls and strips the /api prefix, because
// the FastAPI routes live at the root (/health, /retrieve, /ask).
//
// The target differs by where Vite runs:
//   - on your machine:      http://localhost:8000 (default)
//   - in docker compose:    http://backend:8000, set via VITE_API_TARGET —
//     inside the frontend container, "localhost" is the container itself,
//     not the backend
const apiTarget = process.env.VITE_API_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
