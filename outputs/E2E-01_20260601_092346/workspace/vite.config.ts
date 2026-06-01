import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000, // Frontend will run on port 3000
  },
  build: {
    outDir: 'dist', // Output directory for production build
  },
  // 환경 변수 로딩을 위한 설정 (Vite는 기본적으로 VITE_ 접두사만 로딩)
  envPrefix: 'REACT_APP_', // REACT_APP_ 접두사 환경 변수도 로딩하도록 설정
});