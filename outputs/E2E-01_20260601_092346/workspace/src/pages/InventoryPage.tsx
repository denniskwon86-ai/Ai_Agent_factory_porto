// src/pages/InventoryPage.tsx
import React, { useState } from 'react';
import {
  Container,
  Typography,
  Box,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  TextField,
  DialogActions,
  Alert,
  Snackbar,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import InventoryList from '../components/InventoryList';
import LoadingSpinner from '../components/common/LoadingSpinner';
import ErrorDisplay from '../components/common/ErrorDisplay';
import { Inventory, InventoryCreate, InventoryUpdate } from '../services/inventoryService';
import { useInventory } from '../hooks/useInventory';

const InventoryPage: React.FC = () => {
  const { inventoryItems, loading, error, createInventory, editInventory, removeInventory, refetchInventory } = useInventory();

  const [openAddDialog, setOpenAddDialog] = useState(false);
  const [openEditDialog, setOpenEditDialog] = useState(false);
  const [selectedInventory, setSelectedInventory] = useState<Inventory | null>(null);

  // State for Add Dialog
  const [newMaterialId, setNewMaterialId] = useState('');
  const [newQuantity, setNewQuantity] = useState<number>(0);
  const [newLocation, setNewLocation] = useState('');

  // State for Edit Dialog
  const [editQuantity, setEditQuantity] = useState<number>(0);
  const [editLocation, setEditLocation] = useState('');

  // Snackbar for success/error messages
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');
  const [snackbarSeverity, setSnackbarSeverity] = useState<'success' | 'error'>('success');

  const handleOpenAddDialog = () => {
    setNewMaterialId('');
    setNewQuantity(0);
    setNewLocation('');
    setOpenAddDialog(true);
  };

  const handleCloseAddDialog = () => {
    setOpenAddDialog(false);
  };

  const handleAddInventory = async () => {
    if (!newMaterialId || newQuantity <= 0 || !newLocation) {
      setSnackbarMessage('Please fill all fields correctly.');
      setSnackbarSeverity('error');
      setSnackbarOpen(true);
      return;
    }

    const newItem: InventoryCreate = {
      material_id: newMaterialId,
      quantity: newQuantity,
      location: newLocation,
    };

    try {
      await createInventory(newItem);
      setSnackbarMessage('Inventory item added successfully!');
      setSnackbarSeverity('success');
      setSnackbarOpen(true);
      handleCloseAddDialog();
    } catch (err: any) {
      setSnackbarMessage(`Failed to add inventory: ${err.message}`);
      setSnackbarSeverity('error');
      setSnackbarOpen(true);
    }
  };

  const handleOpenEditDialog = (item: Inventory) => {
    setSelectedInventory(item);
    setEditQuantity(item.quantity);
    setEditLocation(item.location);
    setOpenEditDialog(true);
  };

  const handleCloseEditDialog = () => {
    setOpenEditDialog(false);
    setSelectedInventory(null);
  };

  const handleUpdateInventory = async () => {
    if (!selectedInventory) return;

    if (editQuantity <= 0 || !editLocation) {
      setSnackbarMessage('Please fill all fields correctly.');
      setSnackbarSeverity('error');
      setSnackbarOpen(true);
      return;
    }

    const updatedData: InventoryUpdate = {
      quantity: editQuantity,
      location: editLocation,
    };

    try {
      await editInventory(selectedInventory.inventory_id, updatedData);
      setSnackbarMessage('Inventory item updated successfully!');
      setSnackbarSeverity('success');
      setSnackbarOpen(true);
      handleCloseEditDialog();
    } catch (err: any) {
      setSnackbarMessage(`Failed to update inventory: ${err.message}`);
      setSnackbarSeverity('error');
      setSnackbarOpen(true);
    }
  };

  const handleDeleteInventory = async (id: string) => {
    if (window.confirm('Are you sure you want to delete this inventory item?')) {
      try {
        await removeInventory(id);
        setSnackbarMessage('Inventory item deleted successfully!');
        setSnackbarSeverity('success');
        setSnackbarOpen(true);
      } catch (err: any) {
        setSnackbarMessage(`Failed to delete inventory: ${err.message}`);
        setSnackbarSeverity('error');
        setSnackbarOpen(true);
      }
    }
  };

  const handleSnackbarClose = (event?: React.SyntheticEvent | Event, reason?: string) => {
    if (reason === 'clickaway') {
      return;
    }
    setSnackbarOpen(false);
  };

  if (loading && inventoryItems.length === 0) { // Only show full spinner on initial load
    return <LoadingSpinner />;
  }

  if (error && inventoryItems.length === 0) { // Only show full error on initial load
    return <ErrorDisplay message={error} />;
  }

  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 4 }}>
        <Typography variant="h4" component="h1">
          Inventory Management
        </Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={handleOpenAddDialog}
        >
          Add New Item
        </Button>
      </Box>

      {error && inventoryItems.length > 0 && ( // Show alert if error occurs after initial load
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {loading && inventoryItems.length > 0 && ( // Show progress indicator if loading after initial load
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Loading updates...
        </Typography>
      )}

      <InventoryList
        inventoryItems={inventoryItems}
        onEdit={handleOpenEditDialog}
        onDelete={handleDeleteInventory}
      />

      <Snackbar open={snackbarOpen} autoHideDuration={6000} onClose={handleSnackbarClose}>
        <Alert onClose={handleSnackbarClose} severity={snackbarSeverity} sx={{ width: '100%' }}>
          {snackbarMessage}
        </Alert>
      </Snackbar>

      {/* Add Inventory Dialog */}
      <Dialog open={openAddDialog} onClose={handleCloseAddDialog}>
        <DialogTitle>Add New Inventory Item</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Material ID"
            type="text"
            fullWidth
            variant="outlined"
            value={newMaterialId}
            onChange={(e) => setNewMaterialId(e.target.value)}
            sx={{ mb: 2 }}
          />
          <TextField
            margin="dense"
            label="Quantity"
            type="number"
            fullWidth
            variant="outlined"
            value={newQuantity}
            onChange={(e) => setNewQuantity(Number(e.target.value))}
            inputProps={{ min: 0 }}
            sx={{ mb: 2 }}
          />
          <TextField
            margin="dense"
            label="Location"
            type="text"
            fullWidth
            variant="outlined"
            value={newLocation}
            onChange={(e) => setNewLocation(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseAddDialog}>Cancel</Button>
          <Button onClick={handleAddInventory} variant="contained">Add</Button>
        </DialogActions>
      </Dialog>

      {/* Edit Inventory Dialog */}
      <Dialog open={openEditDialog} onClose={handleCloseEditDialog}>
        <DialogTitle>Edit Inventory Item</DialogTitle>
        <DialogContent>
          {selectedInventory && (
            <>
              <TextField
                margin="dense"
                label="Material Name"
                type="text"
                fullWidth
                variant="outlined"
                value={selectedInventory.material.name}
                disabled // Material Name은 편집 불가
                sx={{ mb: 2 }}
              />
              <TextField
                margin="dense"
                label="Quantity"
                type="number"
                fullWidth
                variant="outlined"
                value={editQuantity}
                onChange={(e) => setEditQuantity(Number(e.target.value))}
                inputProps={{ min: 0 }}
                sx={{ mb: 2 }}
              />
              <TextField
                margin="dense"
                label="Location"
                type="text"
                fullWidth
                variant="outlined"
                value={editLocation}
                onChange={(e) => setEditLocation(e.target.value)}
              />
            </>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseEditDialog}>Cancel</Button>
          <Button onClick={handleUpdateInventory} variant="contained">Update</Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

export default InventoryPage;