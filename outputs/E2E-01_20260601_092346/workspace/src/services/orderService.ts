import apiClient from './apiClient';

    export interface Order {
      orderId?: number;
      orderDate: string;
      status: string; // e.g., PENDING, PROCESSING, SHIPPED, DELIVERED, CANCELLED
      // Add other relevant fields like customer details, total amount, etc. if available in backend
    }

    export interface OrderItem {
      orderItemId?: number;
      orderId: number;
      materialId: number;
      quantity: number;
      price: number;
    }

    export interface OrderPagination {
      pageNumber: number;
      pageSize: number;
      totalPages: number;
      totalElements: number;
    }

    export interface OrderListResponse {
      content: Order[];
      pageable: {
        pageNumber: number;
        pageSize: number;
        totalPages: number;
        totalElements: number;
      };
    }

    const BASE_URL = '/orders';

    export const getOrders = async (page: number = 0, size: number = 10): Promise<OrderListResponse> => {
      const response = await apiClient.get<OrderListResponse>(`${BASE_URL}`, {
        params: { page, size },
      });
      return response.data;
    };

    export const getOrderById = async (id: number): Promise<Order> => {
      const response = await apiClient.get<Order>(`${BASE_URL}/${id}`);
      return response.data;
    };

    export const createOrder = async (order: Omit<Order, 'orderId' | 'status'> & { items: Omit<OrderItem, 'orderItemId' | 'orderId'>[] }): Promise<Order> => {
      const response = await apiClient.post<Order>(`${BASE_URL}`, order);
      return response.data;
    };

    export const updateOrderStatus = async (id: number, status: string): Promise<Order> => {
      const response = await apiClient.patch<Order>(`${BASE_URL}/${id}/status`, { status });
      return response.data;
    };

    export const deleteOrder = async (id: number): Promise<void> => {
      await apiClient.delete(`${BASE_URL}/${id}`);
    };