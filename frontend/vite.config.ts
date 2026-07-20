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
      '/presentation': 'http://127.0.0.1:54321',
      '/catalog': 'http://127.0.0.1:54321',
      '/command': 'http://127.0.0.1:54321',
      '/assets/pets': 'http://127.0.0.1:54321',
    }
  }
});
