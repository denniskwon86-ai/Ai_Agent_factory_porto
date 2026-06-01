import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { Order, OrderPagination, fetchOrders, updateOrderStatus, deleteOrder } from '../services/orderService';
import { DEFAULT_PAGE_SIZE, DEFAULT_PAGE_NUMBER } from '../config/constants';

interface OrderState {
  orders: Order[];
  loading: boolean;
  error: string | null;
  pagination: {
    pageNumber: number;
    pageSize: number;
    totalPages: number;
    totalElements: number;
  };
}

const initialState: OrderState = {
  orders: [],
  loading: false,
  error: null,
  pagination: {
    pageNumber: DEFAULT_PAGE_NUMBER,
    pageSize: DEFAULT_PAGE_SIZE,
    totalPages: 0,
    totalElements: 0,
  },
};

export const loadOrders = createAsyncThunk(
  'orders/loadOrders',
  async (params: { page?: number; size?: number }, { rejectWithValue }) => {
    try {
      const response = await fetchOrders(params.page ?? DEFAULT_PAGE_NUMBER, params.size ?? DEFAULT_PAGE_SIZE);
      return response;
    } catch (error: any) {
      return rejectWithValue(error.message || 'Failed to fetch orders');
    }
  }
);

export const updateOrderById = createAsyncThunk(
  'orders/updateOrderById',
  async ({ id, status }: { id: number; status: string }, { rejectWithValue }) => {
    try {
      const updatedOrder = await updateOrderStatus(id, status);
      return updatedOrder;
    } catch (error: any) {
      return rejectWithValue(error.message || 'Failed to update order status');
    }
  }
);

export const deleteExistingOrder = createAsyncThunk(
  'orders/deleteExistingOrder',
  async (id: number, { rejectWithValue }) => {
    try {
      await deleteOrder(id);
      return id; // Return the ID of the deleted order
    } catch (error: any) {
      return rejectWithValue(error.message || 'Failed to delete order');
    }
  }
);

const orderSlice = createSlice({
  name: 'orders',
  initialState,
  reducers: {
    // Reducers for synchronous actions can be defined here if needed
  },
  extraReducers: (builder) => {
    builder
      // Load Orders
      .addCase(loadOrders.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(loadOrders.fulfilled, (state, action: PayloadAction<OrderPagination>) => {
        state.loading = false;
        state.orders = action.payload.content;
        state.pagination = {
          pageNumber: action.payload.number,
          pageSize: action.payload.size,
          totalPages: action.payload.totalPages,
          totalElements: action.payload.totalElements,
        };
      })
      .addCase(loadOrders.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      // Update Order Status
      .addCase(updateOrderById.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(updateOrderById.fulfilled, (state, action: PayloadAction<Order>) => {
        state.loading = false;
        const index = state.orders.findIndex(o => o.orderId === action.payload.orderId);
        if (index !== -1) {
          state.orders[index] = action.payload;
        }
      })
      .addCase(updateOrderById.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      // Delete Order
      .addCase(deleteExistingOrder.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(deleteExistingOrder.fulfilled, (state, action: PayloadAction<number>) => {
        state.loading = false;
        state.orders = state.orders.filter(o => o.orderId !== action.payload);
        // Adjust pagination if the last item was deleted
        if (state.orders.length === 0 && state.pagination.pageNumber > 0 && state.pagination.totalPages > 0) {
          state.pagination.pageNumber--;
        }
      })
      .addCase(deleteExistingOrder.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      });
  },
});

export default orderSlice.reducer;