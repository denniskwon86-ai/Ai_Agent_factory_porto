// src/store/index.ts
import { configureStore } from '@reduxjs/toolkit';
import inventoryReducer from './slices/inventorySlice';

export const store = configureStore({
  reducer: {
    inventory: inventoryReducer,
  },
  // Optionally add middleware, devTools, etc.
  devTools: process.env.NODE_ENV !== 'production',
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;