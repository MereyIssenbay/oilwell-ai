import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

const proxy = { '/api': { target: 'http://127.0.0.1:8001', changeOrigin: false, rewrite: (path: string) => path.replace(/^\/api/, '') } };
export default defineConfig({
  plugins: [react()],
  server: { host: '127.0.0.1', port: 5173, strictPort: true, proxy },
  preview: { host: '127.0.0.1', port: 5173, strictPort: true, proxy },
  test: { environment: 'jsdom', include: ['src/**/*.test.{ts,tsx}'], setupFiles: ['src/test-setup.ts'] },
  build: { chunkSizeWarningLimit: 1500 },
});
