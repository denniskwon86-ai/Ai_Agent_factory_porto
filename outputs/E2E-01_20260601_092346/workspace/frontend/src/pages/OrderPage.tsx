import React, { useState, useEffect } from 'react';
import {
  Box, Typography, Button, List, ListItem, ListItemText, ListItemSecondaryAction,
  IconButton, Dialog, DialogTitle, DialogContent, DialogActions, TextField,
  FormControl, InputLabel, Select, MenuItem, Snackbar, Alert, Chip
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import AddIcon from '@mui/icons-material/Add';
import RemoveIcon from '@mui/icons-material/Remove';
import axiosInstance from '../api/axiosInstance';
import {
  Order, OrderItem, Material, OrderStatus,
  CreateOrderPayload, CreateOrderItemPayload, UpdateOrderStatusPayload
} from '../types';

interface NewOrderItemInput {
  materialId: number | '';
  quantity: number | '';
  pricePerUnit: number | '';
}

const OrderPage: React.FC = () => {
  const [orders, setOrders] = useState<Order[]>([]);
  const [materials, setMaterials] = useState<Material[]>([]);
  const [openCreateDialog, setOpenCreateDialog] = useState(false);
  const [openUpdateStatusDialog, setOpenUpdateStatusDialog] = useState(false);
  const [newOrderItems, setNewOrderItems] = useState<NewOrderItemInput[]>([{ materialId: '', quantity: '', pricePerUnit: '' }]);
  const [currentOrder, setCurrentOrder] = useState<Order | null>(null);
  const [selectedStatus, setSelectedStatus] = useState<OrderStatus>(OrderStatus.PENDING);
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');
  const [snackbarSeverity, setSnackbarSeverity] = useState<'success' | 'error'>('success');

  useEffect(() => {
    fetchOrders();
    fetchMaterials();
  }, []);

  const fetchOrders = async () => {
    try {
      const response = await axiosInstance.get<Order[]>('/orders');
      setOrders(response.data);
    } catch (error) {
      console.error('Error fetching orders:', error);
      showSnackbar('Failed to fetch orders.', 'error');
    }
  };

  const fetchMaterials = async () => {
    try {
      const response = await axiosInstance.get<Material[]>('/materials');
      setMaterials(response.data);
    } catch (error) {
      console.error('Error fetching materials:', error);
      showSnackbar('Failed to fetch materials.', 'error');
    }
  };

  const handleOpenCreateDialog = () => {
    setNewOrderItems([{ materialId: '', quantity: '', pricePerUnit: '' }]);
    setOpenCreateDialog(true);
  };

  const handleCloseCreateDialog = () => {
    setOpenCreateDialog(false);
  };

  const handleOpenUpdateStatusDialog = (order: Order) => {
    setCurrentOrder(order);
    setSelectedStatus(order.status);
    setOpenUpdateStatusDialog(true);
  };

  const handleCloseUpdateStatusDialog = () => {
    setOpenUpdateStatusDialog(false);
    setCurrentOrder(null);
  };

  const handleAddItem = () => {
    setNewOrderItems([...newOrderItems, { materialId: '', quantity: '', pricePerUnit: '' }]);
  };

  const handleRemoveItem = (index: number) => {
    const updatedItems = newOrderItems.filter((_, i) => i !== index);
    setNewOrderItems(updatedItems);
  };

  const handleOrderItemChange = (index: number, field: keyof NewOrderItemInput, value: any) => {
    const updatedItems = [...newOrderItems];
    updatedItems[index] = { ...updatedItems[index], [field]: value };
    setNewOrderItems(updatedItems);
  };

  const handleCreateOrder = async () => {
    try {
      const payload: CreateOrderPayload = {
        order_items: newOrderItems.map(item => {
          if (item.materialId === '' || item.quantity === '' || item.pricePerUnit === '') {
            throw new Error('All order item fields must be filled.');
          }
          return {
            material_id: Number(item.materialId),
            quantity: Number(item.quantity),
            price_per_unit: Number(item.pricePerUnit),
          };
        }),
      };
      await axiosInstance.post('/orders', payload);
      showSnackbar('Order created successfully!', 'success');
      fetchOrders();
      handleCloseCreateDialog();
    } catch (error: any) {
      const errorMessage = error.response?.data?.detail || error.message || 'An unexpected error occurred.';
      showSnackbar(`Failed to create order: ${errorMessage}`, 'error');
      console.error('Error creating order:', error);
    }
  };

  const handleUpdateOrderStatus = async () => {
    if (!currentOrder) return;
    try {
      const payload: UpdateOrderStatusPayload = { status: selectedStatus };
      await axiosInstance.patch(`/orders/${currentOrder.id}/status`, payload);
      showSnackbar('Order status updated successfully!', 'success');
      fetchOrders();
      handleCloseUpdateStatusDialog();
    } catch (error: any) {
      const errorMessage = error.response?.data?.detail || 'An unexpected error occurred.';
      showSnackbar(`Failed to update order status: ${errorMessage}`, 'error');
      console.error('Error updating order status:', error);
    }
  };

  const handleDeleteOrder = async (id: number) => {
    try {
      await axiosInstance.delete(`/orders/${id}`);
      showSnackbar('Order deleted successfully!', 'success');
      fetchOrders();
    } catch (error: any) {
      const errorMessage = error.response?.data?.detail || 'An unexpected error occurred.';
      showSnackbar(`Failed to delete order: ${errorMessage}`, 'error');
      console.error('Error deleting order:', error);
    }
  };

  const showSnackbar = (message: string, severity: 'success' | 'error') => {
    setSnackbarMessage(message);
    setSnackbarSeverity(severity);
    setSnackbarOpen(true);
  };

  const handleCloseSnackbar = () => {
    setSnackbarOpen(false);
  };

  const getStatusColor = (status: OrderStatus) => {
    switch (status) {
      case OrderStatus.PENDING: return 'info';
      case OrderStatus.PROCESSING: return 'warning';
      case OrderStatus.COMPLETED: return 'success';
      case OrderStatus.CANCELLED: return 'error';
      default: return 'default';
    }
  };

  return (
    <Box sx={{ my: 4 }}>
      <Typography variant="h4" component="h1" gutterBottom>
        Order Management
      </Typography>
      <Button variant="contained" color="primary" onClick={handleOpenCreateDialog} sx={{ mb: 2 }}>
        Create New Order
      </Button>

      <List>
        {orders.map((order) => (
          <ListItem key={order.id} divider>
            <ListItemText
              primary={`Order #${order.id} - ${new Date(order.order_date).toLocaleString()}`}
              secondary={
                <Box>
                  <Chip label={order.status} color={getStatusColor(order.status)} size="small" sx={{ mr: 1 }} />
                  <Typography component="span" variant="body2" color="text.secondary">
                    Items: {order.order_items.map(item => `${item.material_name || `Material ID: ${item.material_id}`} (${item.quantity})`).join(', ')}
                  </Typography>
                </Box>
              }
            />
            <ListItemSecondaryAction>
              <Button size="small" onClick={() => handleOpenUpdateStatusDialog(order)}>
                Update Status
              </Button>
              <IconButton edge="end" aria-label="delete" onClick={() => handleDeleteOrder(order.id)}>
                <DeleteIcon />
              </IconButton>
            </ListItemSecondaryAction>
          </ListItem>
        ))}
      </List>

      {/* Create Order Dialog */}
      <Dialog open={openCreateDialog} onClose={handleCloseCreateDialog} fullWidth maxWidth="md">
        <DialogTitle>Create New Order</DialogTitle>
        <DialogContent>
          {newOrderItems.map((item, index) => (
            <Box key={index} sx={{ display: 'flex', gap: 2, mb: 2, alignItems: 'center' }}>
              <FormControl fullWidth margin="dense" variant="standard" sx={{ flex: 3 }}>
                <InputLabel id={`material-select-label-${index}`}>Material</InputLabel>
                <Select
                  labelId={`material-select-label-${index}`}
                  id={`material-select-${index}`}
                  value={item.materialId}
                  label="Material"
                  onChange={(e) => handleOrderItemChange(index, 'materialId', e.target.value as number)}
                >
                  {materials.map((material) => (
                    <MenuItem key={material.id} value={material.id}>
                      {material.name}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <TextField
                margin="dense"
                label="Quantity"
                type="number"
                fullWidth
                variant="standard"
                value={item.quantity}
                onChange={(e) => handleOrderItemChange(index, 'quantity', Number(e.target.value))}
                inputProps={{ min: 1 }}
                sx={{ flex: 1 }}
              />
              <TextField
                margin="dense"
                label="Price/Unit"
                type="number"
                fullWidth
                variant="standard"
                value={item.pricePerUnit}
                onChange={(e) => handleOrderItemChange(index, 'pricePerUnit', Number(e.target.value))}
                inputProps={{ min: 0, step: "0.01" }}
                sx={{ flex: 1 }}
              />
              <IconButton onClick={() => handleRemoveItem(index)} color="error" disabled={newOrderItems.length === 1}>
                <RemoveIcon />
              </IconButton>
            </Box>
          ))}
          <Button startIcon={<AddIcon />} onClick={handleAddItem} sx={{ mt: 1 }}>
            Add Another Item
          </Button>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseCreateDialog}>Cancel</Button>
          <Button onClick={handleCreateOrder}>Create Order</Button>
        </DialogActions>
      </Dialog>

      {/* Update Order Status Dialog */}
      <Dialog open={openUpdateStatusDialog} onClose={handleCloseUpdateStatusDialog}>
        <DialogTitle>Update Order Status</DialogTitle>
        <DialogContent>
          <Typography variant="subtitle1" gutterBottom>
            Order ID: {currentOrder?.id}
          </Typography>
          <FormControl fullWidth margin="dense" variant="standard">
            <InputLabel id="status-select-label">Status</InputLabel>
            <Select
              labelId="status-select-label"
              id="status-select"
              value={selectedStatus}
              label="Status"
              onChange={(e) => setSelectedStatus(e.target.value as OrderStatus)}
            >
              {Object.values(OrderStatus).map((status) => (
                <MenuItem key={status} value={status}>
                  {status}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseUpdateStatusDialog}>Cancel</Button>
          <Button onClick={handleUpdateOrderStatus}>Update Status</Button>
        </DialogActions>
      </Dialog>

      <Snackbar open={snackbarOpen} autoHideDuration={6000} onClose={handleCloseSnackbar}>
        <Alert onClose={handleCloseSnackbar} severity={snackbarSeverity} sx={{ width: '100%' }}>
          {snackbarMessage}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default OrderPage;