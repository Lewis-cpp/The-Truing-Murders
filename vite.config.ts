import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  root: fileURLToPath(new URL('./src/frontend', import.meta.url)),
  publicDir: fileURLToPath(new URL('./assets/frontend', import.meta.url)),
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: { '/api': 'http://127.0.0.1:8000' },
    fs: {
      allow: ['src/frontend', 'assets/frontend', 'node_modules'],
    },
  },
  preview: { host: '127.0.0.1', port: 4173, strictPort: true },
  build: {
    outDir: fileURLToPath(new URL('./dist/frontend', import.meta.url)),
    emptyOutDir: true,
  },
  test: {
    root: fileURLToPath(new URL('.', import.meta.url)),
    environment: 'jsdom',
    include: ['tests/frontend/**/*.test.ts'],
    restoreMocks: true,
  },
})
