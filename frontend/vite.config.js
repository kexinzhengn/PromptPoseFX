import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    // p5 is loaded on demand as an isolated Effect runtime chunk.
    chunkSizeWarningLimit: 1500,
  },
  server: {
    port: 5200,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5800',
        changeOrigin: true,
      },
    },
  },
})
