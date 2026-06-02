import apiClient from './api';

interface Product {
  product_id: number;
  product_code: string;
  product_name: string;
  unit_of_measure: string;
}

export const fetchProducts = async (): Promise<Product[]> => {
  const response = await apiClient.get<Product[]>('/products');
  return response.data;
};

// Add other product-related API calls here