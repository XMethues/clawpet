import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: '/',
  build: {
    outDir: '../clawchat_pet/web',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:54321',
      '/state': 'http://127.0.0.1:54321',
      '/cultivation': 'http://127.0.0.1:54321',
    }
  }
});
