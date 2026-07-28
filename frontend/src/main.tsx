import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { installFetchInterceptor } from './lib/api'

// [Phase 2] fetch 를 1회 래핑해 우리 백엔드 요청에만 사용자 식별 헤더를 붙인다.
// raw fetch() 가 78곳에 흩어져 있어 개별 수정으로는 반드시 누락이 생긴다 — 여기서 한 번에 덮는다.
installFetchInterceptor()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
