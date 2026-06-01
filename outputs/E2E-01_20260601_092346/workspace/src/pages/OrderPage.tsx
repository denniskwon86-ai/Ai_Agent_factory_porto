import React, { useEffect, useState } from 'react';
import {
  Typography, Box, Button, TextField, Dialog, DialogActions, DialogContent,
  DialogTitle, List, ListItem, ListItemText, ListItemSecondaryAction, IconButton,
  Alert, Snackbar, Select, MenuItem, InputLabel, FormControl, Chip
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import AddIcon from '@mui/icons-material/Add';
import RemoveIcon from '@mui/icons-material/Remove';
import axiosInstance from '../api/axiosInstance';

interface Material {
  materialId: number;
  name: string;
}

interface OrderItem {
  orderItemId?: number;
  materialId: number;
  materialName?: string; // For display
  quantity: number;
  pricePerUnit: number;
}

interface Order {
  orderId: number;
  orderDate: string;
  status: 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'CANCELLED';
  orderItems: OrderItem[];
}

const OrderPage: React.FC = () => {
  const [orders, setOrders] = useState<Order[]>([]);
  const [materials, setMaterials] = useState<Material[]>([]);
  const [openCreateDialog, setOpenCreateDialog] = useState(false);
  const [openUpdateStatusDialog, setOpenUpdateStatusDialog] = useState(false);
  const [currentOrder, setCurrentOrder] = useState<Order | null>(null);
  const [newOrderItems, setNewOrderItems] = useState<OrderItem[]>([]);
  const [selectedStatus, setSelectedStatus] = useState<Order['status']>('PENDING');
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');
  const [snackbarSeverity, setSnackbarSeverity] = useState<'success' | 'error'>('success');

  useEffect(() => {
    fetchMaterials();
    fetchOrders();
  }, []);

  const fetchMaterials = async () => {
    try {
      const response = await axiosInstance.get<Material[]>('/materials');
      setMaterials(response.data);
    } catch (error) {
      showSnackbar('Failed to fetch materials for order creation.', 'error');
      console.error('Error fetching materials:', error);
    }
  };

  const fetchOrders = async () => {
    try {
      const response = await axiosInstance.get<Order[]>('/orders');
      const ordersWithMaterialNames = response.data.map(order => ({
        ...order,
        orderItems: order.orderItems.map(item => ({
          ...item,
          materialName: materials.find(mat => mat.materialId === item.materialId)?.name || 'Unknown Material'
        }))
      }));
      setOrders(ordersWithMaterialNames);
    } catch (error) {
      showSnackbar('Failed to fetch orders.', 'error');
      console.error('Error fetching orders:', error);
    }
  };

  const handleOpenCreateDialog = () => {
    setNewOrderItems([{ materialId: '', quantity: 1, pricePerUnit: 0 } as unknown as OrderItem]);
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
  };

  const handleAddItem = () => {
    setNewOrderItems([...newOrderItems, { materialId: '', quantity: 1, pricePerUnit: 0 } as unknown as OrderItem]);
  };

  const handleRemoveItem = (index: number) => {
    const updatedItems = [...newOrderItems];
    updatedItems.splice(index, 1);
    setNewOrderItems(updatedItems);
  };

  const handleOrderItemChange = (index: number, field: keyof OrderItem, value: any) => {
    const updatedItems = [...newOrderItems];
    updatedItems[index] = { ...updatedItems[index], [field]: value };
    setNewOrderItems(updatedItems);
  };

  const handleCreateOrder = async () => {
    try {
      const payload = {
        orderItems: newOrderItems.map(item => ({
          materialId: Number(item.materialId),
          quantity: Number(item.quantity),
          pricePerUnit: Number(item.pricePerUnit),
        })),
      };
      await axiosInstance.post('/orders', payload);
      showSnackbar('Order created successfully!', 'success');
      fetchOrders();
      handleCloseCreateDialog();
    } catch (error: any) {
      const errorMessage = error.response?.data?.message || 'An unexpected error occurred.';
      showSnackbar(`Failed to create order: ${errorMessage}`, 'error');
      console.error('Error creating order:', error);
    }
  };

  const handleUpdateOrderStatus = async () => {
    if (!currentOrder) return;
    try {
      await axiosInstance.patch(`/orders/${currentOrder.orderId}/status`, { status: selectedStatus });
      showSnackbar('Order status updated successfully!', 'success');
      fetchOrders();
      handleCloseUpdateStatusDialog();
    } catch (error: any) {
      const errorMessage = error.response?.data?.message || 'An unexpected error occurred.';
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
      const errorMessage = error.response?.data?.message || 'An unexpected error occurred.';
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

  const getStatusColor = (status: Order['status']) => {
    switch (status) {
      case 'PENDING': return 'info';
      case 'PROCESSING': return 'warning';
      case 'COMPLETED': return 'success';
      case 'CANCELLED': return 'error';
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
          <ListItem key={order.orderId} divider>
            <ListItemText
              primary={`Order #${order.orderId} - ${new Date(order.orderDate).toLocaleString()}`}
              secondary={
                <Box>
                  <Chip label={order.status} color={getStatusColor(order.status)} size="small" sx={{ mr: 1 }} />
                  <Typography component="span" variant="body2" color="text.secondary">
                    Items: {order.orderItems.map(item => `${item.materialName} (${item.quantity})`).join(', ')}
                  </Typography>
                </Box>
              }
            />
            <ListItemSecondaryAction>
              <Button size="small" onClick={() => handleOpenUpdateStatusDialog(order)}>
                Update Status
              </Button>
              <IconButton edge="end" aria-label="delete" onClick={() => handleDeleteOrder(order.orderId)}>
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
                    <MenuItem key={material.materialId} value={material.materialId}>
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
            Order ID: {currentOrder?.orderId}
          </Typography>
          <FormControl fullWidth margin="dense" variant="standard">
            <InputLabel id="status-select-label">Status</InputLabel>
            <Select
              labelId="status-select-label"
              id="status-select"
              value={selectedStatus}
              label="Status"
              onChange={(e) => setSelectedStatus(e.target.value as Order['status'])}
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

// Define OrderStatus enum for frontend use
enum OrderStatus {
  PENDING = 'PENDING',
  PROCESSING = 'PROCESSING',
  COMPLETED = 'COMPLETED',
  CANCELLED = 'CANCELLED',
}

export default OrderPage;