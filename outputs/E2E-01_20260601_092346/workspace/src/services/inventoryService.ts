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