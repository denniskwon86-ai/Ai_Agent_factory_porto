import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { Inventory, InventoryPagination, fetchInventories, createInventory, updateInventory, deleteInventory } from '../services/inventoryService';
import { DEFAULT_PAGE_SIZE, DEFAULT_PAGE_NUMBER } from '../config/constants';

interface InventoryState {
  inventories: Inventory[];
  loading: boolean;
  error: string | null;
  pagination: {
    pageNumber: number;
    pageSize: number;
    totalPages: number;
    totalElements: number;
  };
}

const initialState: InventoryState = {
  inventories: [],
  loading: false,
  error: null,
  pagination: {
    pageNumber: DEFAULT_PAGE_NUMBER,
    pageSize: DEFAULT_PAGE_SIZE,
    totalPages: 0,
    totalElements: 0,
  },
};

export const loadInventories = createAsyncThunk(
  'inventories/loadInventories',
  async (params: { page?: number; size?: number }, { rejectWithValue }) => {
    try {
      const response = await fetchInventories(params.page ?? DEFAULT_PAGE_NUMBER, params.size ?? DEFAULT_PAGE_SIZE);
      return response;
    } catch (error: any) {
      return rejectWithValue(error.message || 'Failed to fetch inventories');
    }
  }
);

export const addInventory = createAsyncThunk(
  'inventories/addInventory',
  async (inventory: Omit<Inventory, 'inventoryId'>, { rejectWithValue }) => {
    try {
      const newInventory = await createInventory(inventory);
      return newInventory;
    } catch (error: any) {
      return rejectWithValue(error.message || 'Failed to add inventory');
    }
  }
);

export const editInventory = createAsyncThunk(
  'inventories/editInventory',
  async ({ id, inventory }: { id: number; inventory: Partial<Inventory> }, { rejectWithValue }) => {
    try {
      const updatedInventory = await updateInventory(id, inventory);
      return updatedInventory;
    } catch (error: any) {
      return rejectWithValue(error.message || 'Failed to update inventory');
    }
  }
);

export const removeInventory = createAsyncThunk(
  'inventories/removeInventory',
  async (id: number, { rejectWithValue }) => {
    try {
      await deleteInventory(id);
      return id; // Return the ID of the deleted inventory
    } catch (error: any) {
      return rejectWithValue(error.message || 'Failed to delete inventory');
    }
  }
);

const inventorySlice = createSlice({
  name: 'inventories',
  initialState,
  reducers: {
    // Reducers for synchronous actions can be defined here if needed
  },
  extraReducers: (builder) => {
    builder
      // Load Inventories
      .addCase(loadInventories.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(loadInventories.fulfilled, (state, action: PayloadAction<InventoryPagination>) => {
        state.loading = false;
        state.inventories = action.payload.content;
        state.pagination = {
          pageNumber: action.payload.number,
          pageSize: action.payload.size,
          totalPages: action.payload.totalPages,
          totalElements: action.payload.totalElements,
        };
      })
      .addCase(loadInventories.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      // Add Inventory
      .addCase(addInventory.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(addInventory.fulfilled, (state, action: PayloadAction<Inventory>) => {
        state.loading = false;
        // Similar to materials, consider refetching or careful state management
      })
      .addCase(addInventory.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      // Edit Inventory
      .addCase(editInventory.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(editInventory.fulfilled, (state, action: PayloadAction<Inventory>) => {
        state.loading = false;
        const index = state.inventories.findIndex(inv => inv.inventoryId === action.payload.inventoryId);
        if (index !== -1) {
          state.inventories[index] = action.payload;
        }
      })
      .addCase(editInventory.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      // Remove Inventory
      .addCase(removeInventory.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(removeInventory.fulfilled, (state, action: PayloadAction<number>) => {
        state.loading = false;
        state.inventories = state.inventories.filter(inv => inv.inventoryId !== action.payload);
        // Adjust pagination if the last item was deleted
        if (state.inventories.length === 0 && state.pagination.pageNumber > 0 && state.pagination.totalPages > 0) {
          state.pagination.pageNumber--;
        }
      })
      .addCase(removeInventory.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      });
  },
});

export default inventorySlice.reducer;