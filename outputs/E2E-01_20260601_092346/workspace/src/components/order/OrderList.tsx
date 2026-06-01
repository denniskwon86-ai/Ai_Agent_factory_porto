import React from 'react';
    import {
      Table,
      TableBody,
      TableCell,
      TableContainer,
      TableHead,
      TableRow,
      Paper,
      Button,
      Typography,
      Box,
      Pagination,
      Chip,
    } from '@mui/material';
    import { useOrders } from '../../hooks/useOrders';
    import LoadingSpinner from '../common/LoadingSpinner';
    import ErrorMessage from '../common/ErrorMessage';
    import { Order } from '../../services/orderService';
    import { ORDER_STATUS } from '../../config/constants';

    const OrderList: React.FC = () => {
      const { orders, loading, error, pagination, loadOrders, updateOrderStatusById, deleteExistingOrder } = useOrders();

      const handlePageChange = (event: React.ChangeEvent<unknown>, page: number) => {
        loadOrders(page - 1, pagination.pageSize); // page is 1-based, API expects 0-based
      };

      const handleDelete = (id: number) => {
        if (window.confirm('Are you sure you want to delete this order?')) {
          deleteExistingOrder(id).catch(err => console.error("Deletion failed:", err));
        }
      };

      const getStatusColor = (status: string) => {
        switch (status) {
          case ORDER_STATUS.PENDING:
            return 'warning';
          case ORDER_STATUS.PROCESSING:
            return 'info';
          case ORDER_STATUS.SHIPPED:
            return 'primary';
          case ORDER_STATUS.DELIVERED:
            return 'success';
          case ORDER_STATUS.CANCELLED:
            return 'error';
          default:
            return 'default';
        }
      };

      if (loading && orders.length === 0) {
        return <LoadingSpinner />;
      }

      if (error) {
        return <ErrorMessage message={error} />;
      }

      return (
        <Box sx={{ mt: 4 }}>
          <Typography variant="h4" gutterBottom>
            Orders
          </Typography>
          <Box sx={{ mb: 2, textAlign: 'right' }}>
            <Button variant="contained" color="primary">
              Create New Order
            </Button>
          </Box>
          <TableContainer component={Paper}>
            <Table sx={{ minWidth: 650 }} aria-label="simple table">
              <TableHead>
                <TableRow>
                  <TableCell>ID</TableCell>
                  <TableCell>Order Date</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {orders.map((order: Order) => (
                  <TableRow key={order.orderId}>
                    <TableCell>{order.orderId || '-'}</TableCell>
                    <TableCell>{new Date(order.orderDate).toLocaleDateString()}</TableCell>
                    <TableCell>
                      <Chip label={order.status} color={getStatusColor(order.status)} />
                    </TableCell>
                    <TableCell>
                      <Button variant="contained" color="primary" sx={{ mr: 1 }}>
                        View Details
                      </Button>
                      {/* Example of updating status - you might want a more robust way */}
                      {order.status !== ORDER_STATUS.SHIPPED && order.status !== ORDER_STATUS.DELIVERED && (
                        <Button variant="contained" color="secondary" sx={{ mr: 1 }} onClick={() => updateOrderStatusById(order.orderId!, ORDER_STATUS.SHIPPED).catch(err => console.error("Update failed:", err))}>
                          Mark as Shipped
                        </Button>
                      )}
                      <Button variant="contained" color="error" onClick={() => handleDelete(order.orderId!)}>
                        Delete
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          {pagination.totalPages > 0 && (
            <Box sx={{ display: 'flex', justifyContent: 'center', mt: 3 }}>
              <Pagination
                count={pagination.totalPages}
                page={pagination.pageNumber + 1} // Pagination component is 1-based
                onChange={handlePageChange}
                color="primary"
              />
            </Box>
          )}
        </Box>
      );
    };

    export default OrderList;