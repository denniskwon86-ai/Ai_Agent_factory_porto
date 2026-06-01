import apiClient from './apiClient';

    export interface Material {
      materialId?: number;
      name: string;
      description?: string;
      stockQuantity: number;
      unit: string;
      status?: string; // e.g., AVAILABLE, LOW_STOCK, OUT_OF_STOCK
    }

    export interface MaterialPagination {
      pageNumber: number;
      pageSize: number;
      totalPages: number;
      totalElements: number;
    }

    export interface MaterialListResponse {
      content: Material[];
      pageable: {
        pageNumber: number;
        pageSize: number;
        totalPages: number;
        totalElements: number;
      };
    }

    const BASE_URL = '/materials';

    export const getMaterials = async (page: number = 0, size: number = 10): Promise<MaterialListResponse> => {
      const response = await apiClient.get<MaterialListResponse>(`${BASE_URL}`, {
        params: { page, size },
      });
      return response.data;
    };

    export const getMaterialById = async (id: number): Promise<Material> => {
      const response = await apiClient.get<Material>(`${BASE_URL}/${id}`);
      return response.data;
    };

    export const createMaterial = async (material: Omit<Material, 'materialId' | 'status'>): Promise<Material> => {
      const response = await apiClient.post<Material>(`${BASE_URL}`, material);
      return response.data;
    };

    export const updateMaterial = async (id: number, material: Partial<Material>): Promise<Material> => {
      const response = await apiClient.put<Material>(`${BASE_URL}/${id}`, material);
      return response.data;
    };

    export const deleteMaterial = async (id: number): Promise<void> => {
      await apiClient.delete(`${BASE_URL}/${id}`);
    };