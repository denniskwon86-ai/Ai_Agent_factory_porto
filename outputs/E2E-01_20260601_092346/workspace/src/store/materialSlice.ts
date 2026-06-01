import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { Material, MaterialPagination, fetchMaterials, createMaterial, updateMaterial, deleteMaterial } from '../services/materialService';
import { DEFAULT_PAGE_SIZE, DEFAULT_PAGE_NUMBER } from '../config/constants';

interface MaterialState {
  materials: Material[];
  loading: boolean;
  error: string | null;
  pagination: {
    pageNumber: number;
    pageSize: number;
    totalPages: number;
    totalElements: number;
  };
}

const initialState: MaterialState = {
  materials: [],
  loading: false,
  error: null,
  pagination: {
    pageNumber: DEFAULT_PAGE_NUMBER,
    pageSize: DEFAULT_PAGE_SIZE,
    totalPages: 0,
    totalElements: 0,
  },
};

export const loadMaterials = createAsyncThunk(
  'materials/loadMaterials',
  async (params: { page?: number; size?: number }, { rejectWithValue }) => {
    try {
      const response = await fetchMaterials(params.page ?? DEFAULT_PAGE_NUMBER, params.size ?? DEFAULT_PAGE_SIZE);
      return response;
    } catch (error: any) {
      return rejectWithValue(error.message || 'Failed to fetch materials');
    }
  }
);

export const addMaterial = createAsyncThunk(
  'materials/addMaterial',
  async (material: Omit<Material, 'materialId'>, { rejectWithValue }) => {
    try {
      const newMaterial = await createMaterial(material);
      return newMaterial;
    } catch (error: any) {
      return rejectWithValue(error.message || 'Failed to add material');
    }
  }
);

export const editMaterial = createAsyncThunk(
  'materials/editMaterial',
  async ({ id, material }: { id: number; material: Partial<Material> }, { rejectWithValue }) => {
    try {
      const updatedMaterial = await updateMaterial(id, material);
      return updatedMaterial;
    } catch (error: any) {
      return rejectWithValue(error.message || 'Failed to update material');
    }
  }
);

export const removeMaterial = createAsyncThunk(
  'materials/removeMaterial',
  async (id: number, { rejectWithValue }) => {
    try {
      await deleteMaterial(id);
      return id; // Return the ID of the deleted material
    } catch (error: any) {
      return rejectWithValue(error.message || 'Failed to delete material');
    }
  }
);

const materialSlice = createSlice({
  name: 'materials',
  initialState,
  reducers: {
    // Reducers for synchronous actions can be defined here if needed
  },
  extraReducers: (builder) => {
    builder
      // Load Materials
      .addCase(loadMaterials.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(loadMaterials.fulfilled, (state, action: PayloadAction<MaterialPagination>) => {
        state.loading = false;
        state.materials = action.payload.content;
        state.pagination = {
          pageNumber: action.payload.number,
          pageSize: action.payload.size,
          totalPages: action.payload.totalPages,
          totalElements: action.payload.totalElements,
        };
      })
      .addCase(loadMaterials.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      // Add Material
      .addCase(addMaterial.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(addMaterial.fulfilled, (state, action: PayloadAction<Material>) => {
        state.loading = false;
        // Optionally, add the new material to the current page or refetch
        // For simplicity, we'll refetch the first page after adding
        // state.materials.push(action.payload); // This would add to the current list
        // To ensure correct pagination, it's better to refetch or manage state carefully
        // For now, let's assume a refetch will happen via loadMaterials if needed
      })
      .addCase(addMaterial.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      // Edit Material
      .addCase(editMaterial.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(editMaterial.fulfilled, (state, action: PayloadAction<Material>) => {
        state.loading = false;
        const index = state.materials.findIndex(m => m.materialId === action.payload.materialId);
        if (index !== -1) {
          state.materials[index] = action.payload;
        }
      })
      .addCase(editMaterial.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      // Remove Material
      .addCase(removeMaterial.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(removeMaterial.fulfilled, (state, action: PayloadAction<number>) => {
        state.loading = false;
        state.materials = state.materials.filter(m => m.materialId !== action.payload);
        // Adjust pagination if the last item was deleted and it was the only one on the last page
        if (state.materials.length === 0 && state.pagination.pageNumber > 0 && state.pagination.totalPages > 0) {
          state.pagination.pageNumber--;
          // Consider refetching the previous page if necessary
        }
      })
      .addCase(removeMaterial.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      });
  },
});

export default materialSlice.reducer;