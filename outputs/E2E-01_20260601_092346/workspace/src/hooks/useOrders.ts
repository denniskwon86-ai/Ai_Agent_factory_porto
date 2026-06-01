import { useState, useEffect, useCallback } from 'react';
    import { Order, OrderPagination, getOrders, deleteOrder, updateOrderStatus } from '../services/orderService';
    import { ORDER_STATUS } from '../config/constants';

    interface UseOrdersResult {
      orders: Order[];
      loading: boolean;
      error: string | null;
      pagination: OrderPagination;
      loadOrders: (page?: number, size?: number) => Promise<void>;
      updateOrderStatusById: (id: number, status: string) => Promise<void>;
      deleteExistingOrder: (id: number) => Promise<void>;
    }

    export const useOrders = (): UseOrdersResult => {
      const [orders, setOrders] = useState<Order[]>([]);
      const [loading, setLoading] = useState<boolean>(true);
      const [error, setError] = useState<string | null>(null);
      const [pagination, setPagination] = useState<OrderPagination>({
        pageNumber: 0,
        pageSize: 10,
        totalPages: 0,
        totalElements: 0,
      });

      const loadOrders = useCallback(async (page: number = 0, size: number = 10) => {
        setLoading(true);
        setError(null);
        try {
          const response = await getOrders(page, size);
          setOrders(response.content);
          setPagination({
            pageNumber: response.pageable.pageNumber,
            pageSize: response.pageable.pageSize,
            totalPages: response.pageable.totalPages,
            totalElements: response.pageable.totalElements,
          });
        } catch (err: any) {
          setError(err.message || 'Failed to load orders.');
        } finally {
          setLoading(false);
        }
      }, []);

      const updateOrderStatusById = useCallback(async (id: number, status: string) => {
        try {
          await updateOrderStatus(id, status);
          setOrders(prevOrders =>
            prevOrders.map(order =>
              order.orderId === id ? { ...order, status: status } : order
            )
          );
        } catch (err: any) {
          setError(err.message || 'Failed to update order status.');
          throw err;
        }
      }, []);

      const deleteExistingOrder = useCallback(async (id: number) => {
        try {
          await deleteOrder(id);
          setOrders(prevOrders => prevOrders.filter(order => order.orderId !== id));
          // Adjust pagination if the last item on the page was deleted
          if (orders.length === 1 && pagination.pageNumber > 0) {
            loadOrders(pagination.pageNumber - 1, pagination.pageSize);
          } else {
            loadOrders(pagination.pageNumber, pagination.pageSize);
          }
        } catch (err: any) {
          setError(err.message || 'Failed to delete order.');
          throw err;
        }
      }, [orders.length, loadOrders, pagination.pageNumber, pagination.pageSize]);

      useEffect(() => {
        loadOrders();
      }, [loadOrders]);

      return {
        orders,
        loading,
        error,
        pagination,
        loadOrders,
        updateOrderStatusById,
        deleteExistingOrder,
      };
    };