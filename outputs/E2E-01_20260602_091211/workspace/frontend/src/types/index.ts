// Centralized type definitions for the frontend application

export interface User {
  user_id: number;
  username: string;
  email: string;
  role: string;
}

export interface Product {
  product_id: number;
  product_code: string;
  product_name: string;
  unit_of_measure: string;
}

export interface Material {
  material_id: number;
  material_code: string;
  material_name: string;
  unit_of_measure: string;
}