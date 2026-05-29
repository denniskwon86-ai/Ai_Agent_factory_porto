## 1. 환경 변수 및 글로벌 설정 (.env / config)

`.env.example` 파일에 다음 내용을 추가합니다.

```dotenv
# .env.example

# API Base URL
REACT_APP_API_URL=http://localhost:8000/api/v1

# Authentication token (if applicable)
# REACT_APP_AUTH_TOKEN=your_default_token
```

`src/config/index.ts` 파일을 생성하여 환경 변수를 로드하고 전역 설정을 관리합니다.

```typescript
// src/config/index.ts

const config = {
  api: {
    baseUrl: process.env.REACT_APP_API_URL || 'http://localhost:8000/api/v1',
  },
  // Add other global configurations here
};

export default config;
```

`src/App.tsx` 파일에서 라우터 설정을 합니다. (React Router DOM 사용 가정)

```typescript
// src/App.tsx
import React from 'react';
import { BrowserRouter as Router, Route, Routes } from 'react-router-dom';
import DashboardPage from './pages/DashboardPage';
import MaterialsPage from './pages/MaterialsPage';
import BomPage from './pages/BomPage';
import InventoryPage from './pages/InventoryPage';
import ProductionPlanPage from './pages/ProductionPlanPage';
import Header from './components/layout/Header'; // Assuming a Header component exists

function App() {
  return (
    <Router>
      <div className="App">
        <Header /> {/* Example: Global Header */}
        <main>
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/materials" element={<MaterialsPage />} />
            <Route path="/bom" element={<BomPage />} />
            <Route path="/inventory" element={<InventoryPage />} />
            <Route path="/production-plan" element={<ProductionPlanPage />} />
            {/* Add other routes as needed */}
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;
```

## 2. API 통신 및 데이터 패칭 모듈 (Services)

`src/services/api.ts` 파일을 생성하여 API 통신을 담당하는 모듈을 구현합니다. Axios를 사용합니다.

```typescript
// src/services/api.ts
import axios, { AxiosInstance, AxiosResponse, AxiosError } from 'axios';
import config from '../config';

// Define common API response structure if known
interface ApiResponse<T> {
  data: T;
  message?: string;
  status?: string;
}

const apiClient: AxiosInstance = axios.create({
  baseURL: config.api.baseUrl,
  headers: {
    'Content-Type': 'application/json',
    // Add authorization headers if needed, e.g., from localStorage or context
    // 'Authorization': `Bearer ${localStorage.getItem('authToken')}`,
  },
});

// Interceptor for request
apiClient.interceptors.request.use(
  (config) => {
    // You can add logic here to modify requests before they are sent
    // For example, adding authentication tokens
    // const token = localStorage.getItem('authToken');
    // if (token) {
    //   config.headers.Authorization = `Bearer ${token}`;
    // }
    return config;
  },
  (error) => {
    // Do something with request error
    return Promise.reject(error);
  }
);

// Interceptor for response
apiClient.interceptors.response.use(
  (response: AxiosResponse<ApiResponse<any>>) => {
    // Handle successful responses, e.g., extracting data
    return response.data;
  },
  (error: AxiosError<ApiResponse<any>>) => {
    // Handle API errors
    let errorMessage = 'An unexpected error occurred.';
    if (error.response) {
      // The request was made and the server responded with a status code
      // that falls out of the range of 2xx
      errorMessage = error.response.data.message || `Error ${error.response.status}: ${error.response.statusText}`;
      console.error('API Error Response:', error.response.data);
    } else if (error.request) {
      // The request was made but no response was received
      errorMessage = 'No response received from server. Please check your connection.';
      console.error('API Error Request:', error.request);
    } else {
      // Something happened in setting up the request that triggered an Error
      errorMessage = error.message;
      console.error('API Error Message:', error.message);
    }

    // You can also implement global error handling here, like showing a toast notification
    // For example: toast.error(errorMessage);

    return Promise.reject(errorMessage);
  }
);

// --- Specific API Service Functions ---

// Example for MRP Calculation
export interface MrpCalculationTriggerParams {
  // Define parameters for triggering MRP calculation
  // e.g., startDate: string; endDate: string;
}

export const triggerMrpCalculation = async (params: MrpCalculationTriggerParams): Promise<any> => {
  try {
    const response = await apiClient.post('/mrp/calculate', params);
    return response; // Or response.data if ApiResponse structure is consistent
  } catch (error) {
    throw error; // Re-throw to be caught by custom hooks
  }
};

// Example for fetching Dashboard data
export interface DashboardData {
  totalMaterials: number;
  upcomingProduction: number;
  lowStockAlerts: number;
  // Add other dashboard metrics
}

export const fetchDashboardData = async (): Promise<DashboardData> => {
  try {
    const response = await apiClient.get<DashboardData>('/dashboard');
    return response;
  } catch (error) {
    throw error;
  }
};

// Example for fetching Materials
export interface Material {
  id: string;
  name: string;
  // ... other material properties
}

export const fetchMaterials = async (): Promise<Material[]> => {
  try {
    const response = await apiClient.get<Material[]>('/materials');
    return response;
  } catch (error) {
    throw error;
  }
};

// Example for fetching BOMs
export interface BomItem {
  id: string;
  materialId: string;
  quantity: number;
  // ... other BOM properties
}

export const fetchBoms = async (): Promise<BomItem[]> => {
  try {
    const response = await apiClient.get<BomItem[]>('/boms');
    return response;
  } catch (error) {
    throw error;
  }
};

// Example for fetching Inventory
export interface InventoryItem {
  materialId: string;
  quantity: number;
  // ... other inventory properties
}

export const fetchInventory = async (): Promise<InventoryItem[]> => {
  try {
    const response = await apiClient.get<InventoryItem[]>('/inventory');
    return response;
  } catch (error) {
    throw error;
  }
};

// Example for fetching Production Plans
export interface ProductionPlan {
  id: string;
  materialId: string;
  quantity: number;
  dueDate: string;
  // ... other production plan properties
}

export const fetchProductionPlans = async (): Promise<ProductionPlan[]> => {
  try {
    const response = await apiClient.get<ProductionPlan[]>('/production-plans');
    return response;
  } catch (error) {
    throw error;
  }
};

// Add more functions for CRUD operations on Materials, BOMs, Inventory, Production Plans
// e.g., createMaterial, updateMaterial, deleteMaterial, etc.
```

## 3. UI 컴포넌트 및 페이지 코드 (Components / Pages)

### `src/hooks/useMrp.ts` (Custom Hook for MRP Logic)

```typescript
// src/hooks/useMrp.ts
import { useState, useCallback } from 'react';
import { triggerMrpCalculation, MrpCalculationTriggerParams } from '../services/api';

interface UseMrpResult {
  isLoading: boolean;
  error: string | null;
  triggerCalculation: (params: MrpCalculationTriggerParams) => Promise<void>;
}

export const useMrp = (): UseMrpResult => {
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const triggerCalculation = useCallback(async (params: MrpCalculationTriggerParams) => {
    setIsLoading(true);
    setError(null);
    try {
      await triggerMrpCalculation(params);
      // Optionally, handle success feedback here or in the component
      console.log('MRP calculation triggered successfully.');
    } catch (err: any) {
      setError(err || 'Failed to trigger MRP calculation.');
      console.error('MRP Trigger Error:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  return {
    isLoading,
    error,
    triggerCalculation,
  };
};
```

### `src/hooks/useDashboard.ts` (Custom Hook for Dashboard Data)

```typescript
// src/hooks/useDashboard.ts
import { useState, useEffect, useCallback } from 'react';
import { fetchDashboardData, DashboardData } from '../services/api';

interface UseDashboardResult {
  dashboardData: DashboardData | null;
  isLoading: boolean;
  error: string | null;
  fetchData: () => Promise<void>;
}

export const useDashboard = (): UseDashboardResult => {
  const [dashboardData, setDashboardData] = useState<DashboardData | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchDashboardData();
      setDashboardData(data);
    } catch (err: any) {
      setError(err || 'Failed to fetch dashboard data.');
      console.error('Dashboard Fetch Error:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return {
    dashboardData,
    isLoading,
    error,
    fetchData,
  };
};
```

### `src/components/ui/Button.tsx` (Reusable UI Component)

```typescript
// src/components/ui/Button.tsx
import React, { ButtonHTMLAttributes } from 'react';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger';
  size?: 'small' | 'medium' | 'large';
  isLoading?: boolean;
}

const Button: React.FC<ButtonProps> = ({
  children,
  variant = 'primary',
  size = 'medium',
  isLoading = false,
  disabled,
  ...props
}) => {
  const baseStyles = 'font-semibold py-2 px-4 rounded focus:outline-none focus:ring-2 focus:ring-opacity-75 transition ease-in-out duration-150';

  const variantStyles = {
    primary: 'bg-blue-500 hover:bg-blue-600 text-white focus:ring-blue-400',
    secondary: 'bg-gray-200 hover:bg-gray-300 text-gray-800 focus:ring-gray-400',
    danger: 'bg-red-500 hover:bg-red-600 text-white focus:ring-red-400',
  };

  const sizeStyles = {
    small: 'text-sm px-2 py-1',
    medium: 'text-base px-4 py-2',
    large: 'text-lg px-6 py-3',
  };

  const disabledStyles = disabled || isLoading ? 'opacity-50 cursor-not-allowed' : '';

  return (
    <button
      className={`${baseStyles} ${variantStyles[variant]} ${sizeStyles[size]} ${disabledStyles}`}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading ? 'Loading...' : children}
    </button>
  );
};

export default Button;
```

### `src/components/ui/Card.tsx` (Reusable UI Component)

```typescript
// src/components/ui/Card.tsx
import React from 'react';

interface CardProps {
  title?: string;
  children: React.ReactNode;
  className?: string;
}

const Card: React.FC<CardProps> = ({ title, children, className }) => {
  return (
    <div className={`bg-white rounded-lg shadow-md p-6 ${className}`}>
      {title && <h3 className="text-lg font-semibold mb-4 text-gray-700">{title}</h3>}
      {children}
    </div>
  );
};

export default Card;
```

### `src/components/dashboard/MrpTriggerForm.tsx` (Dashboard Specific Component)

```typescript
// src/components/dashboard/MrpTriggerForm.tsx
import React, { useState } from 'react';
import Button from '../ui/Button';
import { MrpCalculationTriggerParams } from '../../services/api';

interface MrpTriggerFormProps {
  onTrigger: (params: MrpCalculationTriggerParams) => Promise<void>;
  isLoading: boolean;
  error: string | null;
}

const MrpTriggerForm: React.FC<MrpTriggerFormProps> = ({ onTrigger, isLoading, error }) => {
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!startDate || !endDate) {
      alert('Please select both start and end dates.');
      return;
    }
    await onTrigger({ startDate, endDate });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <h4 className="text-md font-semibold text-gray-700">Trigger MRP Calculation</h4>
      <div>
        <label htmlFor="startDate" className="block text-sm font-medium text-gray-700">Start Date</label>
        <input
          type="date"
          id="startDate"
          value={startDate}
          onChange={(e) => setStartDate(e.target.value)}
          className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-300 focus:ring focus:ring-indigo-200 focus:ring-opacity-50"
          required
        />
      </div>
      <div>
        <label htmlFor="endDate" className="block text-sm font-medium text-gray-700">End Date</label>
        <input
          type="date"
          id="endDate"
          value={endDate}
          onChange={(e) => setEndDate(e.target.value)}
          className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-300 focus:ring focus:ring-indigo-200 focus:ring-opacity-50"
          required
        />
      </div>
      {error && <p className="text-red-500 text-sm">{error}</p>}
      <Button type="submit" isLoading={isLoading} variant="primary">
        Calculate MRP
      </Button>
    </form>
  );
};

export default MrpTriggerForm;
```

### `src/components/dashboard/DashboardMetrics.tsx` (Dashboard Specific Component)

```typescript
// src/components/dashboard/DashboardMetrics.tsx
import React from 'react';
import Card from '../ui/Card';
import { DashboardData } from '../../services/api';

interface DashboardMetricsProps {
  data: DashboardData | null;
  isLoading: boolean;
  error: string | null;
}

const DashboardMetrics: React.FC<DashboardMetricsProps> = ({ data, isLoading, error }) => {
  if (isLoading) {
    return <Card title="Dashboard Metrics">Loading metrics...</Card>;
  }

  if (error) {
    return <Card title="Dashboard Metrics"><p className="text-red-500">Error: {error}</p></Card>;
  }

  if (!data) {
    return <Card title="Dashboard Metrics">No data available.</Card>;
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      <Card title="Total Materials">
        <p className="text-4xl font-bold text-blue-600">{data.totalMaterials}</p>
      </Card>
      <Card title="Upcoming Production">
        <p className="text-4xl font-bold text-green-600">{data.upcomingProduction}</p>
      </Card>
      <Card title="Low Stock Alerts">
        <p className="text-4xl font-bold text-red-600">{data.lowStockAlerts}</p>
      </Card>
      {/* Add more metric cards as needed */}
    </div>
  );
};

export default DashboardMetrics;
```

### `src/pages/DashboardPage.tsx` (Page Component)

```typescript
// src/pages/DashboardPage.tsx
import React from 'react';
import { useMrp } from '../hooks/useMrp';
import { useDashboard } from '../hooks/useDashboard';
import MrpTriggerForm from '../components/dashboard/MrpTriggerForm';
import DashboardMetrics from '../components/dashboard/DashboardMetrics';
import Card from '../components/ui/Card';

const DashboardPage: React.FC = () => {
  const { isLoading: isMrpLoading, error: mrpError, triggerCalculation } = useMrp();
  const { dashboardData, isLoading: isDashboardLoading, error: dashboardError, fetchData: refreshDashboard } = useDashboard();

  // Combine loading states for a more general loading indicator if needed
  const overallLoading = isMrpLoading || isDashboardLoading;

  return (
    <div className="container mx-auto p-4">
      <h1 className="text-3xl font-bold mb-6 text-gray-800">MRP Dashboard</h1>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 mb-8">
        <div className="lg:col-span-2">
          <DashboardMetrics
            data={dashboardData}
            isLoading={isDashboardLoading}
            error={dashboardError}
          />
        </div>
        <div className="lg:col-span-1">
          <Card>
            <MrpTriggerForm
              onTrigger={triggerCalculation}
              isLoading={isMrpLoading}
              error={mrpError}
            />
          </Card>
        </div>
      </div>

      {/* Placeholder for Charts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card title="MRP Calculation Results (Chart Placeholder)">
          <div className="h-64 bg-gray-200 flex items-center justify-center rounded-md">
            Chart will be rendered here.
          </div>
        </Card>
        <Card title="Inventory Levels (Chart Placeholder)">
          <div className="h-64 bg-gray-200 flex items-center justify-center rounded-md">
            Chart will be rendered here.
          </div>
        </Card>
      </div>

      {/* Add more sections for filtering and detailed views */}
    </div>
  );
};

export default DashboardPage;
```

### `src/pages/MaterialsPage.tsx` (Page Component - Example)

```typescript
// src/pages/MaterialsPage.tsx
import React, { useState, useEffect } from 'react';
import { fetchMaterials, Material } from '../services/api';
import Card from '../components/ui/Card';
import Button from '../components/ui/Button';

const MaterialsPage: React.FC = () => {
  const [materials, setMaterials] = useState<Material[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const loadMaterials = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchMaterials();
      setMaterials(data);
    } catch (err: any) {
      setError(err || 'Failed to fetch materials.');
      console.error('Materials Fetch Error:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadMaterials();
  }, []);

  return (
    <div className="container mx-auto p-4">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold text-gray-800">Materials Management</h1>
        <Button onClick={loadMaterials} variant="secondary">Refresh</Button>
        {/* Add Button for "Add New Material" */}
      </div>

      {isLoading && <p>Loading materials...</p>}
      {error && <p className="text-red-500">Error: {error}</p>}

      {!isLoading && !error && materials.length === 0 && (
        <p>No materials found. Add some!</p>
      )}

      {!isLoading && !error && materials.length > 0 && (
        <Card>
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">ID</th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>
                {/* Add more table headers for material properties */}
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {materials.map((material) => (
                <tr key={material.id}>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{material.id}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{material.name}</td>
                  {/* Render other material properties */}
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                    {/* Add Edit/Delete buttons */}
                    <Button variant="secondary" size="small" className="mr-2">Edit</Button>
                    <Button variant="danger" size="small">Delete</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
};

export default MaterialsPage;
```

### `src/pages/BomPage.tsx` (Page Component - Example)

```typescript
// src/pages/BomPage.tsx
import React, { useState, useEffect } from 'react';
import { fetchBoms, BomItem } from '../services/api';
import Card from '../components/ui/Card';
import Button from '../components/ui/Button';

const BomPage: React.FC = () => {
  const [boms, setBoms] = useState<BomItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const loadBoms = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchBoms();
      setBoms(data);
    } catch (err: any) {
      setError(err || 'Failed to fetch BOMs.');
      console.error('BOMs Fetch Error:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadBoms();
  }, []);

  return (
    <div className="container mx-auto p-4">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold text-gray-800">Bill of Materials (BOM)</h1>
        <Button onClick={loadBoms} variant="secondary">Refresh</Button>
        {/* Add Button for "Add New BOM Item" */}
      </div>

      {isLoading && <p>Loading BOMs...</p>}
      {error && <p className="text-red-500">Error: {error}</p>}

      {!isLoading && !error && boms.length === 0 && (
        <p>No BOM items found. Add some!</p>
      )}

      {!isLoading && !error && boms.length > 0 && (
        <Card>
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">ID</th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Material ID</th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Quantity</th>
                {/* Add more table headers for BOM properties */}
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {boms.map((bomItem) => (
                <tr key={bomItem.id}>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{bomItem.id}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{bomItem.materialId}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{bomItem.quantity}</td>
                  {/* Render other BOM properties */}
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                    {/* Add Edit/Delete buttons */}
                    <Button variant="secondary" size="small" className="mr-2">Edit</Button>
                    <Button variant="danger" size="small">Delete</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
};

export default BomPage;
```

### `src/pages/InventoryPage.tsx` (Page Component - Example)

```typescript
// src/pages/InventoryPage.tsx
import React, { useState, useEffect } from 'react';
import { fetchInventory, InventoryItem } from '../services/api';
import Card from '../components/ui/Card';
import Button from '../components/ui/Button';

const InventoryPage: React.FC = () => {
  const [inventory, setInventory] = useState<InventoryItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const loadInventory = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchInventory();
      setInventory(data);
    } catch (err: any) {
      setError(err || 'Failed to fetch inventory.');
      console.error('Inventory Fetch Error:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadInventory();
  }, []);

  return (
    <div className="container mx-auto p-4">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold text-gray-800">Inventory Management</h1>
        <Button onClick={loadInventory} variant="secondary">Refresh</Button>
        {/* Add Button for "Add New Inventory Item" */}
      </div>

      {isLoading && <p>Loading inventory...</p>}
      {error && <p className="text-red-500">Error: {error}</p>}

      {!isLoading && !error && inventory.length === 0 && (
        <p>No inventory items found. Add some!</p>
      )}

      {!isLoading && !error && inventory.length > 0 && (
        <Card>
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Material ID</th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Quantity</th>
                {/* Add more table headers for inventory properties */}
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {inventory.map((item) => (
                <tr key={item.materialId}>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{item.materialId}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{item.quantity}</td>
                  {/* Render other inventory properties */}
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                    {/* Add Edit/Delete buttons */}
                    <Button variant="secondary" size="small" className="mr-2">Edit</Button>
                    <Button variant="danger" size="small">Delete</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
};

export default InventoryPage;
```

### `src/pages/ProductionPlanPage.tsx` (Page Component - Example)

```typescript
// src/pages/ProductionPlanPage.tsx
import React, { useState, useEffect } from 'react';
import { fetchProductionPlans, ProductionPlan } from '../services/api';
import Card from '../components/ui/Card';
import Button from '../components/ui/Button';

const ProductionPlanPage: React.FC = () => {
  const [plans, setPlans] = useState<ProductionPlan[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const loadProductionPlans = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchProductionPlans();
      setPlans(data);
    } catch (err: any) {
      setError(err || 'Failed to fetch production plans.');
      console.error('Production Plans Fetch Error:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadProductionPlans();
  }, []);

  return (
    <div className="container mx-auto p-4">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold text-gray-800">Production Plans</h1>
        <Button onClick={loadProductionPlans} variant="secondary">Refresh</Button>
        {/* Add Button for "Create New Production Plan" */}
      </div>

      {isLoading && <p>Loading production plans...</p>}
      {error && <p className="text-red-500">Error: {error}</p>}

      {!isLoading && !error && plans.length === 0 && (
        <p>No production plans found. Create some!</p>
      )}

      {!isLoading && !error && plans.length > 0 && (
        <Card>
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">ID</th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Material ID</th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Quantity</th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Due Date</th>
                {/* Add more table headers for production plan properties */}
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {plans.map((plan) => (
                <tr key={plan.id}>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{plan.id}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{plan.materialId}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{plan.quantity}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{plan.dueDate}</td>
                  {/* Render other production plan properties */}
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                    {/* Add Edit/Delete buttons */}
                    <Button variant="secondary" size="small" className="mr-2">Edit</Button>
                    <Button variant="danger" size="small">Delete</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
};

export default ProductionPlanPage;
```

*(Note: `Header` component is assumed to exist in `src/components/layout/Header.tsx` and would contain navigation links to the different pages.)*