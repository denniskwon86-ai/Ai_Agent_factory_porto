// src/components/OrderList.tsx
import React, { useEffect, useState } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import { RootState, AppDispatch } from '@/store';
import { fetchOrders, createOrder, updateOrderStatus, deleteOrder } from '@/store/slices/orderSlice';
import { fetchMaterials } from '@/store/slices/materialSlice'; // To get material names for order items
import {
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper,
  Button, TextField, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, Box, Select, MenuItem, InputLabel, FormControl, Typography
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import CancelIcon from '@mui/icons-material/Cancel';

interface OrderItemForm {
  material_id: number;
  quantity: number;
}

interface OrderForm {
  order_items: OrderItemForm[];
}

const OrderList: React.FC = () => {
  const dispatch: AppDispatch = useDispatch();
  const { orders, status, error } = useSelector((state: RootState) => state.orders);
  const { materials } = useSelector((state: RootState) => state.materials);

  const [open, setOpen] = useState(false);
  const [formValues, setFormValues] = useState<OrderForm>({ order_items: [{ material_id: 0, quantity: 0 }] });

  useEffect(() => {
    if (status === 'idle') {
      dispatch(fetchOrders());
      dispatch(fetchMaterials()); // Fetch materials for order item selection
    }
  }, [status, dispatch]);

  const getMaterialName = (materialId: number) => {
    const material = materials.find(m => m.material_id === materialId);
    return material ? material.name : 'Unknown Material';
  };

  const handleClickOpen = () => {
    setFormValues({ order_items: [{ material_id: materials[0]?.material_id || 0, quantity: 1 }] });
    setOpen(true);
  };

  const handleClose = () => {
    setOpen(false);
    setFormValues({ order_items: [{ material_id: 0, quantity: 0 }] });
  };

  const handleOrderItemChange = (index: number, e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement> | any) => {
    const { name, value } = e.target;
    const newOrderItems = [...formValues.order_items];
    newOrderItems[index] = {
      ...newOrderItems[index],
      [name]: name === 'quantity' || name === 'material_id' ? parseInt(value) : value,
    };
    setFormValues({ ...formValues, order_items: newOrderItems });
  };

  const addOrderItem = () => {
    setFormValues((prev) => ({
      ...prev,
      order_items: [...prev.order_items, { material_id: materials[0]?.material_id || 0, quantity: 1 }],
    }));
  };

  const removeOrderItem = (index: number) => {
    setFormValues((prev) => ({
      ...prev,
      order_items: prev.order_items.filter((_, i) => i !== index),
    }));
  };

  const handleSubmit = () => {
    dispatch(createOrder(formValues));
    handleClose();
  };

  const handleUpdateStatus = (id: number, newStatus: 'PENDING' | 'COMPLETED' | 'CANCELLED') => {
    if (window.confirm(`Are you sure you want to change order ${id} status to ${newStatus}?`)) {
      dispatch(updateOrderStatus({ id, status: newStatus }));
    }
  };

  const handleDelete = (id: number) => {
    if (window.confirm('Are you sure you want to delete this order?')) {
      dispatch(deleteOrder(id));
    }
  };

  if (status === 'loading') return <p>Loading orders...</p>;
  if (status === 'failed') return <p>Error: {error}</p>;

  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
        <h2>Orders</h2>
        <Button variant="contained" startIcon={<AddIcon />} onClick={handleClickOpen}>
          Create Order
        </Button>
      </Box>

      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>ID</TableCell>
              <TableCell>Date</TableCell>
              <TableCell>Status</TableCell>
              <TableCell align="right">Total Amount</TableCell>
              <TableCell>Items</TableCell>
              <TableCell align="center">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {orders.map((order) => (
              <TableRow key={order.order_id}>
                <TableCell>{order.order_id}</TableCell>
                <TableCell>{new Date(order.order_date).toLocaleDateString()}</TableCell>
                <TableCell>{order.status}</TableCell>
                <TableCell align="right">${order.total_amount.toFixed(2)}</TableCell>
                <TableCell>
                  {order.order_items.map((item, idx) => (
                    <Typography key={idx} variant="body2">
                      {getMaterialName(item.material_id)} x {item.quantity} (${item.unit_price.toFixed(2)} each)
                    </Typography>
                  ))}
                </TableCell>
                <TableCell align="center">
                  {order.status === 'PENDING' && (
                    <>
                      <IconButton color="success" onClick={() => handleUpdateStatus(order.order_id, 'COMPLETED')}>
                        <CheckCircleIcon />
                      </IconButton>
                      <IconButton color="warning" onClick={() => handleUpdateStatus(order.order_id, 'CANCELLED')}>
                        <CancelIcon />
                      </IconButton>
                    </>
                  )}
                  <IconButton color="error" onClick={() => handleDelete(order.order_id)}>
                    <DeleteIcon />
                  </IconButton>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      <Dialog open={open} onClose={handleClose} fullWidth maxWidth="md">
        <DialogTitle>Create New Order</DialogTitle>
        <DialogContent>
          {formValues.order_items.map((item, index) => (
            <Box key={index} display="flex" gap={2} alignItems="center" mb={2}>
              <FormControl fullWidth margin="dense" variant="standard">
                <InputLabel id={`material-select-label-${index}`}>Material</InputLabel>
                <Select
                  labelId={`material-select-label-${index}`}
                  id={`material-select-${index}`}
                  name="material_id"
                  value={item.material_id}
                  onChange={(e) => handleOrderItemChange(index, e)}
                  label="Material"
                >
                  {materials.map((material) => (
                    <MenuItem key={material.material_id} value={material.material_id}>
                      {material.name}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <TextField
                margin="dense"
                name="quantity"
                label="Quantity"
                type="number"
                fullWidth
                variant="standard"
                value={item.quantity}
                onChange={(e) => handleOrderItemChange(index, e)}
                inputProps={{ min: 1 }}
              />
              <IconButton color="error" onClick={() => removeOrderItem(index)} disabled={formValues.order_items.length === 1}>
                <DeleteIcon />
              </IconButton>
            </Box>
          ))}
          <Button startIcon={<AddIcon />} onClick={addOrderItem} sx={{ mt: 2 }}>
            Add Another Item
          </Button>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClose}>Cancel</Button>
          <Button onClick={handleSubmit}>Create Order</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default OrderList;