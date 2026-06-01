// src/store/slices/inventorySlice.ts
import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { Inventory, InventoryCreate, InventoryUpdate, inventoryService } from '../../services/inventoryService';

interface InventoryState {
  items: Inventory[];
  loading: boolean;
  error: string | null;
}

const initialState: InventoryState = {
  items: [],
  loading: false,
  error: null,
};

// Async Thunks
export const fetchInventoryItems = createAsyncThunk<Inventory[], void, { rejectValue: string }>(
  'inventory/fetchInventoryItems',
  async (_, { rejectWithValue }) => {
    try {
      const response = await inventoryService.getAllInventory();
      return response;
    } catch (error: any) {
      return rejectWithValue(error.message || 'Failed to fetch inventory items');
    }
  }
);

export const addInventoryItem = createAsyncThunk<Inventory, InventoryCreate, { rejectValue: string }>(
  'inventory/addInventoryItem',
  async (newItem, { rejectWithValue }) => {
    try {
      const response = await inventoryService.createInventory(newItem);
      return response;
    } catch (error: any) {
      return rejectWithValue(error.message || 'Failed to add inventory item');
    }
  }
);

export const updateInventoryItem = createAsyncThunk<Inventory, { id: string; data: InventoryUpdate }, { rejectValue: string }>(
  'inventory/updateInventoryItem',
  async ({ id, data }, { rejectWithValue }) => {
    try {
      const response = await inventoryService.updateInventory(id, data);
      return response;
    } catch (error: any) {
      return rejectWithValue(error.message || 'Failed to update inventory item');
    }
  }
);

export const deleteInventoryItem = createAsyncThunk<string, string, { rejectValue: string }>(
  'inventory/deleteInventoryItem',
  async (id, { rejectWithValue }) => {
    try {
      await inventoryService.deleteInventory(id);
      return id; // Return the ID of the deleted item
    } catch (error: any) {
      return rejectWithValue(error.message || 'Failed to delete inventory item');
    }
  }
);

const inventorySlice = createSlice({
  name: 'inventory',
  initialState,
  reducers: {
    // Synchronous reducers can be added here if needed
  },
  extraReducers: (builder) => {
    builder
      // Fetch All
      .addCase(fetchInventoryItems.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchInventoryItems.fulfilled, (state, action: PayloadAction<Inventory[]>) => {
        state.loading = false;
        state.items = action.payload;
      })
      .addCase(fetchInventoryItems.rejected, (state, action: PayloadAction<string | undefined>) => {
        state.loading = false;
        state.error = action.payload || 'Unknown error';
      })
      // Add Item
      .addCase(addInventoryItem.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(addInventoryItem.fulfilled, (state, action: PayloadAction<Inventory>) => {
        state.loading = false;
        state.items.push(action.payload);
      })
      .addCase(addInventoryItem.rejected, (state, action: PayloadAction<string | undefined>) => {
        state.loading = false;
        state.error = action.payload || 'Unknown error';
      })
      // Update Item
      .addCase(updateInventoryItem.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(updateInventoryItem.fulfilled, (state, action: PayloadAction<Inventory>) => {
        state.loading = false;
        const index = state.items.findIndex((item) => item.inventory_id === action.payload.inventory_id);
        if (index !== -1) {
          state.items[index] = action.payload;
        }
      })
      .addCase(updateInventoryItem.rejected, (state, action: PayloadAction<string | undefined>) => {
        state.loading = false;
        state.error = action.payload || 'Unknown error';
      })
      // Delete Item
      .addCase(deleteInventoryItem.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(deleteInventoryItem.fulfilled, (state, action: PayloadAction<string>) => {
        state.loading = false;
        state.items = state.items.filter((item) => item.inventory_id !== action.payload);
      })
      .addCase(deleteInventoryItem.rejected, (state, action: PayloadAction<string | undefined>) => {
        state.loading = false;
        state.error = action.payload || 'Unknown error';
      });
  },
});

export default inventorySlice.reducer;