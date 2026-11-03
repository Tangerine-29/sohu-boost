import { defineConfig } from 'vite'

export default defineConfig({
  base: './',
  build: {
    outDir: '../web_dist',
    emptyOutDir: true,
    target: 'es2020',
    rollupOptions: {
      output: {
        manualChunks: { three: ['three'] },
      },
    },
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8790',
    },
  },
})
