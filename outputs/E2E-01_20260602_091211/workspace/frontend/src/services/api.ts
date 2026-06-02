import axios from 'axios';

const apiClient = axios.create({
  baseURL: '/api/v1', // Matches the proxy in vite.config.ts
  headers: {
    'Content-Type': 'application/json',
  },
});

export default apiClient;