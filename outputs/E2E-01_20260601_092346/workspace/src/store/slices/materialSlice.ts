// src/store/slices/materialSlice.ts
import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import axios from 'axios';
import { API_BASE_URL } from '@/config'; // Alias usage

interface Material {
  material_id: number;
  name: string;
  description?: string;
  unit_price: number;
  created_at: string;
  updated_at: string;
}

interface MaterialState {
  materials: Material[];
  status: 'idle' | 'loading' | 'succeeded' | 'failed';
  error: string | null;
}

const initialState: MaterialState = {
  materials: [],
  status: 'idle',
  error: null,
};

// Async Thunks
export const fetchMaterials = createAsyncThunk('materials/fetchMaterials', async () => {
  const response = await axios.get(`${API_BASE_URL}/materials`);
  return response.data;
});

export const createMaterial = createAsyncThunk('materials/createMaterial', async (newMaterial: Omit<Material, 'material_id' | 'created_at' | 'updated_at'>) => {
  const response = await axios.post(`${API_BASE_URL}/materials`, newMaterial);
  return response.data;
});

export const updateMaterial = createAsyncThunk('materials/updateMaterial', async ({ id, updatedMaterial }: { id: number; updatedMaterial: Partial<Material> }) => {
  const response = await axios.patch(`${API_BASE_URL}/materials/${id}`, updatedMaterial);
  return response.data;
});

export const deleteMaterial = createAsyncThunk('materials/deleteMaterial', async (id: number) => {
  await axios.delete(`${API_BASE_URL}/materials/${id}`);
  return id;
});

const materialSlice = createSlice({
  name: 'materials',
  initialState,
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchMaterials.pending, (state) => {
        state.status = 'loading';
      })
      .addCase(fetchMaterials.fulfilled, (state, action: PayloadAction<Material[]>) => {
        state.status = 'succeeded';
        state.materials = action.payload;
      })
      .addCase(fetchMaterials.rejected, (state, action) => {
        state.status = 'failed';
        state.error = action.error.message || 'Failed to fetch materials';
      })
      .addCase(createMaterial.fulfilled, (state, action: PayloadAction<Material>) => {
        state.materials.push(action.payload);
      })
      .addCase(updateMaterial.fulfilled, (state, action: PayloadAction<Material>) => {
        const index = state.materials.findIndex((m) => m.material_id === action.payload.material_id);
        if (index !== -1) {
          state.materials[index] = action.payload;
        }
      })
      .addCase(deleteMaterial.fulfilled, (state, action: PayloadAction<number>) => {
        state.materials = state.materials.filter((m) => m.material_id !== action.payload);
      });
  },
});

export default materialSlice.reducer;