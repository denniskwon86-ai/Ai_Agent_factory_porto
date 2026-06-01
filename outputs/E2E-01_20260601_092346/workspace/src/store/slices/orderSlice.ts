// src/store/slices/orderSlice.ts
import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import axios from 'axios';
import { API_BASE_URL } from '@/config';

interface OrderItem {
  order_item_id: number;
  material_id: number;
  quantity: number;
  unit_price: number;
  material_name?: string; // For display purposes
}

interface Order {
  order_id: number;
  order_date: string;
  status: 'PENDING' | 'COMPLETED' | 'CANCELLED';
  total_amount: number;
  order_items: OrderItem[];
}

interface OrderState {
  orders: Order[];
  status: 'idle' | 'loading' | 'succeeded' | 'failed';
  error: string | null;
}

const initialState: OrderState = {
  orders: [],
  status: 'idle',
  error: null,
};

export const fetchOrders = createAsyncThunk('orders/fetchOrders', async () => {
  const response = await axios.get(`${API_BASE_URL}/orders`);
  return response.data;
});

export const createOrder = createAsyncThunk('orders/createOrder', async (newOrder: { order_items: Omit<OrderItem, 'order_item_id'>[] }) => {
  const response = await axios.post(`${API_BASE_URL}/orders`, newOrder);
  return response.data;
});

export const updateOrderStatus = createAsyncThunk('orders/updateOrderStatus', async ({ id, status }: { id: number; status: Order['status'] }) => {
  const response = await axios.patch(`${API_BASE_URL}/orders/${id}/status`, { status });
  return response.data;
});

export const deleteOrder = createAsyncThunk('orders/deleteOrder', async (id: number) => {
  await axios.delete(`${API_BASE_URL}/orders/${id}`);
  return id;
});

const orderSlice = createSlice({
  name: 'orders',
  initialState,
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchOrders.pending, (state) => {
        state.status = 'loading';
      })
      .addCase(fetchOrders.fulfilled, (state, action: PayloadAction<Order[]>) => {
        state.status = 'succeeded';
        state.orders = action.payload;
      })
      .addCase(fetchOrders.rejected, (state, action) => {
        state.status = 'failed';
        state.error = action.error.message || 'Failed to fetch orders';
      })
      .addCase(createOrder.fulfilled, (state, action: PayloadAction<Order>) => {
        state.orders.push(action.payload);
      })
      .addCase(updateOrderStatus.fulfilled, (state, action: PayloadAction<Order>) => {
        const index = state.orders.findIndex((order) => order.order_id === action.payload.order_id);
        if (index !== -1) {
          state.orders[index] = action.payload;
        }
      })
      .addCase(deleteOrder.fulfilled, (state, action: PayloadAction<number>) => {
        state.orders = state.orders.filter((order) => order.order_id !== action.payload);
      });
  },
});

export default orderSlice.reducer;