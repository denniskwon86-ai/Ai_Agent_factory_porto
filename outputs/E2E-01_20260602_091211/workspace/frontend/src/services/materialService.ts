import apiClient from './api';

interface Material {
  material_id: number;
  material_code: string;
  material_name: string;
  unit_of_measure: string;
}

export const fetchMaterials = async (): Promise<Material[]> => {
  const response = await apiClient.get<Material[]>('/materials');
  return response.data;
};

// Add other material-related API calls here