// src/services/apiClient.ts
import axios from 'axios';
import { envConfig } from '../config/env';

const apiClient = axios.create({
  baseURL: envConfig.API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10000, // 10 seconds timeout
});

// Request interceptor for logging or adding auth tokens
apiClient.interceptors.request.use(
  (config) => {
    // Example: Add Authorization token if available
    // const token = localStorage.getItem('authToken');
    // if (token) {
    //   config.headers.Authorization = `Bearer ${token}`;
    // }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    if (error.response) {
      // The request was made and the server responded with a status code
      // that falls out of the range of 2xx
      console.error('API Error Response:', error.response.data);
      console.error('Status:', error.response.status);
      console.error('Headers:', error.response.headers);
      return Promise.reject(new Error(error.response.data.message || `API Error: ${error.response.status}`));
    } else if (error.request) {
      // The request was made but no response was received
      console.error('API Error Request:', error.request);
      return Promise.reject(new Error('No response received from server. Please check your network connection.'));
    } else {
      // Something happened in setting up the request that triggered an Error
      console.error('API Error Message:', error.message);
      return Promise.reject(new Error(`Request setup error: ${error.message}`));
    }
  }
);

export default apiClient;