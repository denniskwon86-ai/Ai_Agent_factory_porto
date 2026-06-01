// src/components/MaterialList.tsx
import React, { useEffect, useState } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import { RootState, AppDispatch } from '@/store';
import { fetchMaterials, createMaterial, updateMaterial, deleteMaterial } from '@/store/slices/materialSlice';
import {
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper,
  Button, TextField, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, Box
} from '@mui/material';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import AddIcon from '@mui/icons-material/Add';

interface MaterialForm {
  name: string;
  description: string;
  unit_price: number;
}

const MaterialList: React.FC = () => {
  const dispatch: AppDispatch = useDispatch();
  const { materials, status, error } = useSelector((state: RootState) => state.materials);

  const [open, setOpen] = useState(false);
  const [currentMaterial, setCurrentMaterial] = useState<MaterialForm & { material_id?: number } | null>(null);
  const [formValues, setFormValues] = useState<MaterialForm>({ name: '', description: '', unit_price: 0 });

  useEffect(() => {
    if (status === 'idle') {
      dispatch(fetchMaterials());
    }
  }, [status, dispatch]);

  const handleClickOpen = (material?: MaterialForm & { material_id?: number }) => {
    if (material) {
      setCurrentMaterial(material);
      setFormValues({
        name: material.name,
        description: material.description || '',
        unit_price: material.unit_price,
      });
    } else {
      setCurrentMaterial(null);
      setFormValues({ name: '', description: '', unit_price: 0 });
    }
    setOpen(true);
  };

  const handleClose = () => {
    setOpen(false);
    setCurrentMaterial(null);
    setFormValues({ name: '', description: '', unit_price: 0 });
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormValues((prev) => ({
      ...prev,
      [name]: name === 'unit_price' ? parseFloat(value) : value,
    }));
  };

  const handleSubmit = () => {
    if (currentMaterial?.material_id) {
      dispatch(updateMaterial({ id: currentMaterial.material_id, updatedMaterial: formValues }));
    } else {
      dispatch(createMaterial(formValues));
    }
    handleClose();
  };

  const handleDelete = (id: number) => {
    if (window.confirm('Are you sure you want to delete this material?')) {
      dispatch(deleteMaterial(id));
    }
  };

  if (status === 'loading') return <p>Loading materials...</p>;
  if (status === 'failed') return <p>Error: {error}</p>;

  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
        <h2>Materials</h2>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => handleClickOpen()}>
          Add Material
        </Button>
      </Box>

      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>ID</TableCell>
              <TableCell>Name</TableCell>
              <TableCell>Description</TableCell>
              <TableCell align="right">Unit Price</TableCell>
              <TableCell align="center">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {materials.map((material) => (
              <TableRow key={material.material_id}>
                <TableCell>{material.material_id}</TableCell>
                <TableCell>{material.name}</TableCell>
                <TableCell>{material.description}</TableCell>
                <TableCell align="right">${material.unit_price.toFixed(2)}</TableCell>
                <TableCell align="center">
                  <IconButton color="primary" onClick={() => handleClickOpen(material)}>
                    <EditIcon />
                  </IconButton>
                  <IconButton color="error" onClick={() => handleDelete(material.material_id)}>
                    <DeleteIcon />
                  </IconButton>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      <Dialog open={open} onClose={handleClose}>
        <DialogTitle>{currentMaterial ? 'Edit Material' : 'Add New Material'}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            name="name"
            label="Material Name"
            type="text"
            fullWidth
            variant="standard"
            value={formValues.name}
            onChange={handleChange}
          />
          <TextField
            margin="dense"
            name="description"
            label="Description"
            type="text"
            fullWidth
            variant="standard"
            value={formValues.description}
            onChange={handleChange}
          />
          <TextField
            margin="dense"
            name="unit_price"
            label="Unit Price"
            type="number"
            fullWidth
            variant="standard"
            value={formValues.unit_price}
            onChange={handleChange}
            inputProps={{ step: "0.01" }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClose}>Cancel</Button>
          <Button onClick={handleSubmit}>{currentMaterial ? 'Update' : 'Add'}</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default MaterialList;