import React, { useEffect, useState } from 'react';
import {
  Typography, Box, Button, TextField, Dialog, DialogActions, DialogContent,
  DialogTitle, List, ListItem, ListItemText, ListItemSecondaryAction, IconButton,
  Alert, Snackbar
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import axiosInstance from '../api/axiosInstance';

interface Material {
  materialId: number;
  name: string;
  description: string;
}

const MaterialPage: React.FC = () => {
  const [materials, setMaterials] = useState<Material[]>([]);
  const [openDialog, setOpenDialog] = useState(false);
  const [currentMaterial, setCurrentMaterial] = useState<Material | null>(null);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');
  const [snackbarSeverity, setSnackbarSeverity] = useState<'success' | 'error'>('success');

  useEffect(() => {
    fetchMaterials();
  }, []);

  const fetchMaterials = async () => {
    try {
      const response = await axiosInstance.get<Material[]>('/materials');
      setMaterials(response.data);
    } catch (error) {
      showSnackbar('Failed to fetch materials.', 'error');
      console.error('Error fetching materials:', error);
    }
  };

  const handleOpenDialog = (material?: Material) => {
    if (material) {
      setCurrentMaterial(material);
      setName(material.name);
      setDescription(material.description);
    } else {
      setCurrentMaterial(null);
      setName('');
      setDescription('');
    }
    setOpenDialog(true);
  };

  const handleCloseDialog = () => {
    setOpenDialog(false);
  };

  const handleSubmit = async () => {
    try {
      if (currentMaterial) {
        // Update material
        await axiosInstance.put(`/materials/${currentMaterial.materialId}`, { name, description });
        showSnackbar('Material updated successfully!', 'success');
      } else {
        // Create new material
        await axiosInstance.post('/materials', { name, description });
        showSnackbar('Material created successfully!', 'success');
      }
      fetchMaterials();
      handleCloseDialog();
    } catch (error: any) {
      const errorMessage = error.response?.data?.message || 'An unexpected error occurred.';
      showSnackbar(`Failed to save material: ${errorMessage}`, 'error');
      console.error('Error saving material:', error);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await axiosInstance.delete(`/materials/${id}`);
      showSnackbar('Material deleted successfully!', 'success');
      fetchMaterials();
    } catch (error: any) {
      const errorMessage = error.response?.data?.message || 'An unexpected error occurred.';
      showSnackbar(`Failed to delete material: ${errorMessage}`, 'error');
      console.error('Error deleting material:', error);
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

  return (
    <Box sx={{ my: 4 }}>
      <Typography variant="h4" component="h1" gutterBottom>
        Material Management
      </Typography>
      <Button variant="contained" color="primary" onClick={() => handleOpenDialog()} sx={{ mb: 2 }}>
        Add New Material
      </Button>

      <List>
        {materials.map((material) => (
          <ListItem key={material.materialId} divider>
            <ListItemText
              primary={material.name}
              secondary={material.description}
            />
            <ListItemSecondaryAction>
              <IconButton edge="end" aria-label="edit" onClick={() => handleOpenDialog(material)}>
                <EditIcon />
              </IconButton>
              <IconButton edge="end" aria-label="delete" onClick={() => handleDelete(material.materialId)}>
                <DeleteIcon />
              </IconButton>
            </ListItemSecondaryAction>
          </ListItem>
        ))}
      </List>

      <Dialog open={openDialog} onClose={handleCloseDialog}>
        <DialogTitle>{currentMaterial ? 'Edit Material' : 'Add New Material'}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Material Name"
            type="text"
            fullWidth
            variant="standard"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <TextField
            margin="dense"
            label="Description"
            type="text"
            fullWidth
            variant="standard"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog}>Cancel</Button>
          <Button onClick={handleSubmit}>{currentMaterial ? 'Update' : 'Add'}</Button>
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

export default MaterialPage;