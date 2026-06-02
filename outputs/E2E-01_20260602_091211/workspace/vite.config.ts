import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      // Proxy API requests to the backend server
      '/api/v1': {
        target: 'http://localhost:8000', // Assuming your FastAPI backend runs on port 8000
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/v1/, '/api/v1'),
      },
    },
  },
  resolve: {
    alias: {
      '@': '/src',
    },
  },
});