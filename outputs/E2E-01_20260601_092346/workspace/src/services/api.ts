import axios, { AxiosInstance, AxiosError } from 'axios';
import { env } from '../config/env';

const API_BASE_URL = env.REACT_APP_API_URL;

const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10000, // 10초 타임아웃
});

// 요청 인터셉터: 인증 토큰 추가 등
api.interceptors.request.use(
  (config) => {
    // 예: const token = localStorage.getItem('authToken');
    // if (token) {
    //   config.headers.Authorization = `Bearer ${token}`;
    // }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 응답 인터셉터: 에러 처리, 로딩 상태 관리 등
api.interceptors.response.use(
  (response) => {
    return response;
  },
  (error: AxiosError) => {
    if (error.response) {
      // 서버가 응답했지만, 상태 코드가 2xx 범위 밖인 경우
      console.error('API Error Response:', error.response.data);
      console.error('Status:', error.response.status);
      console.error('Headers:', error.response.headers);
      // 특정 상태 코드에 따른 전역 처리 (예: 401 Unauthorized -> 로그인 페이지로 리다이렉트)
      if (error.response.status === 401) {
        // window.location.href = '/login';
      }
    } else if (error.request) {
      // 요청이 이루어졌지만 응답을 받지 못한 경우 (네트워크 오류 등)
      console.error('API Error Request:', error.request);
    } else {
      // 요청 설정 중 문제가 발생한 경우
      console.error('API Error Message:', error.message);
    }
    return Promise.reject(error);
  }
);

export default api;