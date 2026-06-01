이전 컴파일 실패에 대한 구체적인 에러 로그가 제공되지 않아 정확한 원인 분석이 어렵습니다. 하지만, `npm run build` 실패는 주로 `package.json` 파일 누락, 필수 의존성 미설치, 애플리케이션 진입점 (`main.tsx`, `App.tsx`) 부재, 환경 변수 설정 오류, 또는 전역 설정 (예: Material-UI `ThemeProvider`, Redux `Provider`) 누락 등에서 발생합니다.

제공된 `Tech Spec`과 이전 출력의 맥락을 고려할 때, 프로젝트의 기본 구조와 필수 설정 파일들이 누락되어 빌드가 실패했을 가능성이 높습니다. 특히 `package.json`, `src/main.tsx`, `src/App.tsx`와 같은 핵심 파일들이 이전 출력에 포함되지 않았습니다.

따라서, 이번 응답에서는 빌드 시스템이 완벽하게 구동될 수 있도록 **누락된 핵심 파일들을 포함하고, 기존에 제공된 컴포넌트들을 새로운 구조에 맞게 통합하는 완전한 프론트엔드 프로젝트 구조를 제공**하겠습니다. 이는 "델타 업데이트"의 개념을 확장하여, 빌드 실패의 근본 원인(핵심 파일 누락)을 해결하는 방향으로 해석합니다.

---

# 1. 환경 변수 및 글로벌 설정 (.env / config)

<file path=".env.template">
# API Base URL for the backend service
# Example: http://localhost:8080/api/v1
REACT_APP_API_URL=
</file>

<file path="src/config/env.ts">
// src/config/env.ts
interface EnvConfig {
  API_BASE_URL: string;
}

const getEnvConfig = (): EnvConfig => {
  const API_BASE_URL = import.meta.env.REACT_APP_API_URL;

  if (!API_BASE_URL) {
    console.error('Environment variable REACT_APP_API_URL is not defined.');
    // In a real application, you might throw an error or provide a default.
    // For now, we'll use an empty string, but this will likely cause API calls to fail.
    // Consider adding a robust error handling or a fallback URL.
    // throw new Error('REACT_APP_API_URL is not defined in the environment variables.');
  }

  return {
    API_BASE_URL: API_BASE_URL || '', // Fallback to empty string if not defined
  };
};

export const envConfig = getEnvConfig();
</file>

<file path="src/config/index.ts">
// src/config/index.ts
// Global constants or configurations not directly from environment variables
export const APP_NAME = "Inventory Management System";
export const API_VERSION = "v1";
</file>

<file path="src/store/index.ts">
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
</file>

<file path="src/store/slices/inventorySlice.ts">
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
</file>

<file path="src/hooks/useInventory.ts">
// src/hooks/useInventory.ts
import { useEffect } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import { RootState, AppDispatch } from '../store';
import {
  fetchInventoryItems,
  addInventoryItem,
  updateInventoryItem,
  deleteInventoryItem,
} from '../store/slices/inventorySlice';
import { InventoryCreate, InventoryUpdate } from '../services/inventoryService';

export const useInventory = () => {
  const dispatch: AppDispatch = useDispatch();
  const { items, loading, error } = useSelector((state: RootState) => state.inventory);

  useEffect(() => {
    dispatch(fetchInventoryItems());
  }, [dispatch]);

  const createInventory = (newItem: InventoryCreate) => {
    return dispatch(addInventoryItem(newItem)).unwrap();
  };

  const editInventory = (id: string, data: InventoryUpdate) => {
    return dispatch(updateInventoryItem({ id, data })).unwrap();
  };

  const removeInventory = (id: string) => {
    return dispatch(deleteInventoryItem(id)).unwrap();
  };

  const refetchInventory = () => {
    dispatch(fetchInventoryItems());
  };

  return {
    inventoryItems: items,
    loading,
    error,
    createInventory,
    editInventory,
    removeInventory,
    refetchInventory,
  };
};
</file>

# 2. API 통신 및 데이터 패칭 모듈 (Services)

<file path="src/services/apiClient.ts">
// src/services/apiClient.ts
import axios from 'axios';
import { envConfig } from '../config/env';

const apiClient = axios.create({
  baseURL: envConfig.API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10000, // 10 seconds timeout
});

// Request interceptor for logging or adding auth tokens
apiClient.interceptors.request.use(
  (config) => {
    // Example: Add Authorization token if available
    // const token = localStorage.getItem('authToken');
    // if (token) {
    //   config.headers.Authorization = `Bearer ${token}`;
    // }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    if (error.response) {
      // The request was made and the server responded with a status code
      // that falls out of the range of 2xx
      console.error('API Error Response:', error.response.data);
      console.error('Status:', error.response.status);
      console.error('Headers:', error.response.headers);
      return Promise.reject(new Error(error.response.data.message || `API Error: ${error.response.status}`));
    } else if (error.request) {
      // The request was made but no response was received
      console.error('API Error Request:', error.request);
      return Promise.reject(new Error('No response received from server. Please check your network connection.'));
    } else {
      // Something happened in setting up the request that triggered an Error
      console.error('API Error Message:', error.message);
      return Promise.reject(new Error(`Request setup error: ${error.message}`));
    }
  }
);

export default apiClient;
</file>

<file path="src/services/inventoryService.ts">
// src/services/inventoryService.ts
import apiClient from './apiClient';

// Data Models
export interface Material {
  material_id: string;
  name: string;
  description: string;
  unit_of_measure: string;
  created_at: string;
  updated_at: string;
}

export interface Inventory {
  inventory_id: string;
  material: Material; // Nested Material object
  quantity: number;
  location: string;
  last_updated: string;
  created_at: string;
}

// DTOs for Create/Update operations
export interface InventoryCreate {
  material_id: string; // Only material_id is needed for creation
  quantity: number;
  location: string;
}

export interface InventoryUpdate {
  quantity?: number;
  location?: string;
}

const INVENTORY_API_BASE_URL = '/inventory'; // Relative path, will be prefixed by apiClient's baseURL

export const inventoryService = {
  /**
   * Fetches all inventory items.
   * @returns Promise<Inventory[]>
   */
  getAllInventory: async (): Promise<Inventory[]> => {
    const response = await apiClient.get<Inventory[]>(INVENTORY_API_BASE_URL);
    return response.data;
  },

  /**
   * Fetches a single inventory item by ID.
   * @param id The ID of the inventory item.
   * @returns Promise<Inventory>
   */
  getInventoryById: async (id: string): Promise<Inventory> => {
    const response = await apiClient.get<Inventory>(`${INVENTORY_API_BASE_URL}/${id}`);
    return response.data;
  },

  /**
   * Creates a new inventory item.
   * @param data The inventory item data to create.
   * @returns Promise<Inventory>
   */
  createInventory: async (data: InventoryCreate): Promise<Inventory> => {
    const response = await apiClient.post<Inventory>(INVENTORY_API_BASE_URL, data);
    return response.data;
  },

  /**
   * Updates an existing inventory item.
   * @param id The ID of the inventory item to update.
   * @param data The partial inventory item data to update.
   * @returns Promise<Inventory>
   */
  updateInventory: async (id: string, data: InventoryUpdate): Promise<Inventory> => {
    const response = await apiClient.put<Inventory>(`${INVENTORY_API_BASE_URL}/${id}`, data);
    return response.data;
  },

  /**
   * Deletes an inventory item by ID.
   * @param id The ID of the inventory item to delete.
   * @returns Promise<void>
   */
  deleteInventory: async (id: string): Promise<void> => {
    await apiClient.delete(`${INVENTORY_API_BASE_URL}/${id}`);
  },
};
</file>

# 3. UI 컴포넌트 및 페이지 코드 (Components / Pages)

<file path="src/components/layout/Header.tsx">
// src/components/layout/Header.tsx
import React from 'react';
import { AppBar, Toolbar, Typography, Box, Button } from '@mui/material';
import { Link } from 'react-router-dom';
import InventoryIcon from '@mui/icons-material/Inventory';
import { APP_NAME } from '../../config';

const Header: React.FC = () => {
  return (
    <AppBar position="static" sx={{ mb: 4 }}>
      <Toolbar>
        <InventoryIcon sx={{ mr: 1 }} />
        <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
          <Link to="/" style={{ textDecoration: 'none', color: 'inherit' }}>
            {APP_NAME}
          </Link>
        </Typography>
        <Box>
          <Button color="inherit" component={Link} to="/">
            Inventory
          </Button>
          {/* Add more navigation links here if needed */}
          {/* <Button color="inherit" component={Link} to="/orders">
            Orders
          </Button> */}
        </Box>
      </Toolbar>
    </AppBar>
  );
};

export default Header;
</file>

<file path="src/pages/InventoryPage.tsx">
// src/pages/InventoryPage.tsx
import React, { useState } from 'react';
import {
  Container,
  Typography,
  Box,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  TextField,
  DialogActions,
  Alert,
  Snackbar,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import InventoryList from '../components/InventoryList';
import LoadingSpinner from '../components/common/LoadingSpinner';
import ErrorDisplay from '../components/common/ErrorDisplay';
import { Inventory, InventoryCreate, InventoryUpdate } from '../services/inventoryService';
import { useInventory } from '../hooks/useInventory';

const InventoryPage: React.FC = () => {
  const { inventoryItems, loading, error, createInventory, editInventory, removeInventory, refetchInventory } = useInventory();

  const [openAddDialog, setOpenAddDialog] = useState(false);
  const [openEditDialog, setOpenEditDialog] = useState(false);
  const [selectedInventory, setSelectedInventory] = useState<Inventory | null>(null);

  // State for Add Dialog
  const [newMaterialId, setNewMaterialId] = useState('');
  const [newQuantity, setNewQuantity] = useState<number>(0);
  const [newLocation, setNewLocation] = useState('');

  // State for Edit Dialog
  const [editQuantity, setEditQuantity] = useState<number>(0);
  const [editLocation, setEditLocation] = useState('');

  // Snackbar for success/error messages
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');
  const [snackbarSeverity, setSnackbarSeverity] = useState<'success' | 'error'>('success');

  const handleOpenAddDialog = () => {
    setNewMaterialId('');
    setNewQuantity(0);
    setNewLocation('');
    setOpenAddDialog(true);
  };

  const handleCloseAddDialog = () => {
    setOpenAddDialog(false);
  };

  const handleAddInventory = async () => {
    if (!newMaterialId || newQuantity <= 0 || !newLocation) {
      setSnackbarMessage('Please fill all fields correctly.');
      setSnackbarSeverity('error');
      setSnackbarOpen(true);
      return;
    }

    const newItem: InventoryCreate = {
      material_id: newMaterialId,
      quantity: newQuantity,
      location: newLocation,
    };

    try {
      await createInventory(newItem);
      setSnackbarMessage('Inventory item added successfully!');
      setSnackbarSeverity('success');
      setSnackbarOpen(true);
      handleCloseAddDialog();
    } catch (err: any) {
      setSnackbarMessage(`Failed to add inventory: ${err.message}`);
      setSnackbarSeverity('error');
      setSnackbarOpen(true);
    }
  };

  const handleOpenEditDialog = (item: Inventory) => {
    setSelectedInventory(item);
    setEditQuantity(item.quantity);
    setEditLocation(item.location);
    setOpenEditDialog(true);
  };

  const handleCloseEditDialog = () => {
    setOpenEditDialog(false);
    setSelectedInventory(null);
  };

  const handleUpdateInventory = async () => {
    if (!selectedInventory) return;

    if (editQuantity <= 0 || !editLocation) {
      setSnackbarMessage('Please fill all fields correctly.');
      setSnackbarSeverity('error');
      setSnackbarOpen(true);
      return;
    }

    const updatedData: InventoryUpdate = {
      quantity: editQuantity,
      location: editLocation,
    };

    try {
      await editInventory(selectedInventory.inventory_id, updatedData);
      setSnackbarMessage('Inventory item updated successfully!');
      setSnackbarSeverity('success');
      setSnackbarOpen(true);
      handleCloseEditDialog();
    } catch (err: any) {
      setSnackbarMessage(`Failed to update inventory: ${err.message}`);
      setSnackbarSeverity('error');
      setSnackbarOpen(true);
    }
  };

  const handleDeleteInventory = async (id: string) => {
    if (window.confirm('Are you sure you want to delete this inventory item?')) {
      try {
        await removeInventory(id);
        setSnackbarMessage('Inventory item deleted successfully!');
        setSnackbarSeverity('success');
        setSnackbarOpen(true);
      } catch (err: any) {
        setSnackbarMessage(`Failed to delete inventory: ${err.message}`);
        setSnackbarSeverity('error');
        setSnackbarOpen(true);
      }
    }
  };

  const handleSnackbarClose = (event?: React.SyntheticEvent | Event, reason?: string) => {
    if (reason === 'clickaway') {
      return;
    }
    setSnackbarOpen(false);
  };

  if (loading && inventoryItems.length === 0) { // Only show full spinner on initial load
    return <LoadingSpinner />;
  }

  if (error && inventoryItems.length === 0) { // Only show full error on initial load
    return <ErrorDisplay message={error} />;
  }

  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 4 }}>
        <Typography variant="h4" component="h1">
          Inventory Management
        </Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={handleOpenAddDialog}
        >
          Add New Item
        </Button>
      </Box>

      {error && inventoryItems.length > 0 && ( // Show alert if error occurs after initial load
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {loading && inventoryItems.length > 0 && ( // Show progress indicator if loading after initial load
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Loading updates...
        </Typography>
      )}

      <InventoryList
        inventoryItems={inventoryItems}
        onEdit={handleOpenEditDialog}
        onDelete={handleDeleteInventory}
      />

      <Snackbar open={snackbarOpen} autoHideDuration={6000} onClose={handleSnackbarClose}>
        <Alert onClose={handleSnackbarClose} severity={snackbarSeverity} sx={{ width: '100%' }}>
          {snackbarMessage}
        </Alert>
      </Snackbar>

      {/* Add Inventory Dialog */}
      <Dialog open={openAddDialog} onClose={handleCloseAddDialog}>
        <DialogTitle>Add New Inventory Item</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Material ID"
            type="text"
            fullWidth
            variant="outlined"
            value={newMaterialId}
            onChange={(e) => setNewMaterialId(e.target.value)}
            sx={{ mb: 2 }}
          />
          <TextField
            margin="dense"
            label="Quantity"
            type="number"
            fullWidth
            variant="outlined"
            value={newQuantity}
            onChange={(e) => setNewQuantity(Number(e.target.value))}
            inputProps={{ min: 0 }}
            sx={{ mb: 2 }}
          />
          <TextField
            margin="dense"
            label="Location"
            type="text"
            fullWidth
            variant="outlined"
            value={newLocation}
            onChange={(e) => setNewLocation(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseAddDialog}>Cancel</Button>
          <Button onClick={handleAddInventory} variant="contained">Add</Button>
        </DialogActions>
      </Dialog>

      {/* Edit Inventory Dialog */}
      <Dialog open={openEditDialog} onClose={handleCloseEditDialog}>
        <DialogTitle>Edit Inventory Item</DialogTitle>
        <DialogContent>
          {selectedInventory && (
            <>
              <TextField
                margin="dense"
                label="Material Name"
                type="text"
                fullWidth
                variant="outlined"
                value={selectedInventory.material.name}
                disabled // Material Name은 편집 불가
                sx={{ mb: 2 }}
              />
              <TextField
                margin="dense"
                label="Quantity"
                type="number"
                fullWidth
                variant="outlined"
                value={editQuantity}
                onChange={(e) => setEditQuantity(Number(e.target.value))}
                inputProps={{ min: 0 }}
                sx={{ mb: 2 }}
              />
              <TextField
                margin="dense"
                label="Location"
                type="text"
                fullWidth
                variant="outlined"
                value={editLocation}
                onChange={(e) => setEditLocation(e.target.value)}
              />
            </>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseEditDialog}>Cancel</Button>
          <Button onClick={handleUpdateInventory} variant="contained">Update</Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

export default InventoryPage;
</file>

<file path="src/components/InventoryList.tsx">
// src/components/InventoryList.tsx
import React from 'react';
import { Grid, Typography, Box } from '@mui/material';
import InventoryItemCard from './InventoryItemCard';
import { Inventory } from '../services/inventoryService';

interface InventoryListProps {
  inventoryItems: Inventory[];
  onEdit: (item: Inventory) => void;
  onDelete: (id: string) => void;
}

const InventoryList: React.FC<InventoryListProps> = ({ inventoryItems, onEdit, onDelete }) => {
  if (inventoryItems.length === 0) {
    return (
      <Box sx={{ mt: 4, textAlign: 'center' }}>
        <Typography variant="h6" color="text.secondary">
          No inventory items found.
        </Typography>
      </Box>
    );
  }

  return (
    <Grid container spacing={3}>
      {inventoryItems.map((item) => (
        <Grid item xs={12} sm={6} md={4} key={item.inventory_id}>
          <InventoryItemCard
            item={item}
            onEdit={onEdit}
            onDelete={onDelete}
          />
        </Grid>
      ))}
    </Grid>
  );
};

export default InventoryList;
</file>

<file path="src/components/InventoryItemCard.tsx">
// src/components/InventoryItemCard.tsx
import React from 'react';
import { Card, CardContent, Typography, CardActions, Button, Box } from '@mui/material';
import { Inventory } from '../services/inventoryService';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';

interface InventoryItemCardProps {
  item: Inventory;
  onEdit: (item: Inventory) => void;
  onDelete: (id: string) => void;
}

const InventoryItemCard: React.FC<InventoryItemCardProps> = ({ item, onEdit, onDelete }) => {
  return (
    <Card sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <CardContent sx={{ flexGrow: 1 }}>
        <Typography variant="h6" component="div" gutterBottom>
          {item.material.name}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Material ID: {item.material.material_id}
        </Typography>
        <Typography variant="body1" sx={{ mt: 1 }}>
          Quantity: <strong>{item.quantity}</strong>
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Location: {item.location}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Last Updated: {new Date(item.last_updated).toLocaleString()}
        </Typography>
      </CardContent>
      <CardActions sx={{ justifyContent: 'flex-end' }}>
        <Button size="small" startIcon={<EditIcon />} onClick={() => onEdit(item)}>
          Edit
        </Button>
        <Button size="small" color="error" startIcon={<DeleteIcon />} onClick={() => onDelete(item.inventory_id)}>
          Delete
        </Button>
      </CardActions>
    </Card>
  );
};

export default InventoryItemCard;
</file>

<file path="src/components/common/LoadingSpinner.tsx">
// src/components/common/LoadingSpinner.tsx
import React from 'react';
import { Box, CircularProgress, Typography } from '@mui/material';

const LoadingSpinner: React.FC = () => {
  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'center',
        height: '100vh',
        width: '100%',
      }}
    >
      <CircularProgress size={60} />
      <Typography variant="h6" sx={{ mt: 2 }}>
        Loading...
      </Typography>
    </Box>
  );
};

export default LoadingSpinner;
</file>

<file path="src/components/common/ErrorDisplay.tsx">
// src/components/common/ErrorDisplay.tsx
import React from 'react';
import { Box, Alert, AlertTitle, Typography } from '@mui/material';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';

interface ErrorDisplayProps {
  message: string;
  title?: string;
}

const ErrorDisplay: React.FC<ErrorDisplayProps> = ({ message, title = 'Error' }) => {
  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'center',
        height: '100vh',
        width: '100%',
        p: 2,
      }}
    >
      <Alert severity="error" icon={<ErrorOutlineIcon fontSize="inherit" />} sx={{ width: '100%', maxWidth: 500 }}>
        <AlertTitle>{title}</AlertTitle>
        <Typography variant="body1">{message}</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          Please try again later or contact support.
        </Typography>
      </Alert>
    </Box>
  );
};

export default ErrorDisplay;
</file>

<file path="src/App.tsx">
// src/App.tsx
import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { ThemeProvider, createTheme, CssBaseline } from '@mui/material';
import { Provider } from 'react-redux';
import { store } from './store';
import InventoryPage from './pages/InventoryPage';
import Header from './components/layout/Header';

// Define a custom Material-UI theme
const theme = createTheme({
  palette: {
    primary: {
      main: '#1976d2', // A shade of blue
    },
    secondary: {
      main: '#dc004e', // A shade of red
    },
    background: {
      default: '#f4f6f8', // Light grey background
    },
  },
  typography: {
    fontFamily: 'Roboto, Arial, sans-serif',
    h4: {
      fontWeight: 600,
    },
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none', // Keep button text as is
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundColor: '#282c34', // Darker header
        },
      },
    },
  },
});

const App: React.FC = () => {
  return (
    <Provider store={store}>
      <ThemeProvider theme={theme}>
        <CssBaseline /> {/* Resets CSS and applies basic Material-UI styles */}
        <Router>
          <Header />
          <Routes>
            <Route path="/" element={<InventoryPage />} />
            {/* Add other routes here */}
            {/* <Route path="/orders" element={<OrdersPage />} /> */}
          </Routes>
        </Router>
      </ThemeProvider>
    </Provider>
  );
};

export default App;
</file>

<file path="src/main.tsx">
// src/main.tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css'; // Global CSS, if any

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
</file>

<file path="src/index.css">
/* src/index.css */
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen',
    'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue',
    sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

code {
  font-family: source-code-pro, Menlo, Monaco, Consolas, 'Courier New',
    monospace;
}
</file>

# [필수 파일 출력 표준 (XML Format)]

<file path="package.json">
{
  "name": "inventory-frontend",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "lint": "eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0",
    "preview": "vite preview"
  },
  "dependencies": {
    "@emotion/react": "^11.11.4",
    "@emotion/styled": "^11.11.5",
    "@mui/icons-material": "^5.15.18",
    "@mui/material": "^5.15.18",
    "@reduxjs/toolkit": "^2.2.5",
    "axios": "^1.7.2",
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-redux": "^9.1.2",
    "react-router-dom": "^6.23.1"
  },
  "devDependencies": {
    "@types/react": "^18.2.66",
    "@types/react-dom": "^18.2.22",
    "@typescript-eslint/eslint-plugin": "^7.2.0",
    "@typescript-eslint/parser": "^7.2.0",
    "@vitejs/plugin-react": "^4.2.1",
    "eslint": "^8.57.0",
    "eslint-plugin-react-hooks": "^4.6.0",
    "eslint-plugin-react-refresh": "^0.4.6",
    "typescript": "^5.2.2",
    "vite": "^5.2.0"
  }
}
</file>

<file path="index.html">
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Inventory Management System</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
</file>

<file path="vite.config.ts">
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000, // Frontend will run on port 3000
  },
  build: {
    outDir: 'dist', // Output directory for production build
  },
  // 환경 변수 로딩을 위한 설정 (Vite는 기본적으로 VITE_ 접두사만 로딩)
  envPrefix: 'REACT_APP_', // REACT_APP_ 접두사 환경 변수도 로딩하도록 설정
});
</file>

<file path="tsconfig.json">
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,

    /* Bundler mode */
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",

    /* Linting */
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,

    /* Redux Toolkit specific */
    "forceConsistentCasingInFileNames": true,
    "esModuleInterop": true
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
</file>

<file path="tsconfig.node.json">
{
  "compilerOptions": {
    "composite": true,
    "tsBuildInfoFile": "./node_modules/.tmp/tsconfig.node.tsbuildinfo",
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "noEmit": true,
    "types": ["node"]
  },
  "include": ["vite.config.ts"]
}
</file>