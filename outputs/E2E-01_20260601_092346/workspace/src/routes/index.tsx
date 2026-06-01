// 현재는 App.tsx에서 직접 라우팅을 처리하고 있으나,
// 애플리케이션 규모가 커질 경우 이 파일에서 중앙 집중식 라우팅 설정을 관리할 수 있습니다.
// 예시:
/*
import React from 'react';
import { Routes, Route } from 'react-router-dom';
import InventoryPage from '../pages/InventoryPage';
import NotFoundPage from '../pages/NotFoundPage'; // 예시

const AppRoutes: React.FC = () => {
  return (
    <Routes>
      <Route path="/" element={<InventoryPage />} />
      <Route path="/inventory" element={<InventoryPage />} />
      // <Route path="/orders" element={<OrdersPage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
};

export default AppRoutes;
*/