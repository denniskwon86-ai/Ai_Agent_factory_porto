// src/main.tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
// @ts-ignore: Ignore missing CSS module declaration for side-effect import
import './index.css'; // Global CSS, if any

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);