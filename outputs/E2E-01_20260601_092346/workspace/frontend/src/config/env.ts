// src/config/env.ts
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
  // Add other environment variables here
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

if (!API_BASE_URL) {
  console.error('VITE_API_BASE_URL is not defined. Please check your .env file.');
}