// src/types/index.ts

export enum OrderStatus {
  PENDING = 'PENDING',
  PROCESSING = 'PROCESSING',
  COMPLETED = 'COMPLETED',
  CANCELLED = 'CANCELLED',
}

export interface Material {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface Inventory {
  id: number;
  material_id: number;
  quantity: number;
  updated_at: string;
}

export interface OrderItem {
  id: number;
  order_id: number;
  material_id: number;
  material_name?: string; // Populated by backend for response
  quantity: number;
  price_per_unit: number;
  created_at: string;
  updated_at: string | null;
}

export interface Order {
  id: number;
  order_date: string;
  status: OrderStatus;
  order_items: OrderItem[];
  created_at: string;
  updated_at: string | null;
}

// Request Payloads
export interface CreateMaterialPayload {
  name: string;
  description?: string;
  initial_inventory_quantity?: number;
}

export interface CreateOrderItemPayload {
  material_id: number;
  quantity: number;
  price_per_unit: number;
}

export interface CreateOrderPayload {
  order_items: CreateOrderItemPayload[];
}

export interface UpdateOrderStatusPayload {
  status: OrderStatus;
}