import { defineConfig } from 'vite'

export default defineConfig({
  build: {
    rollupOptions: {
      output: { manualChunks: { katex: ['katex'] } },
    },
  },
  server: {
    host: '127.0.0.1',
    proxy: {
      '/api': process.env.AI_TUTOR_DEV_API ?? 'http://127.0.0.1:8000',
    },
  },
})
