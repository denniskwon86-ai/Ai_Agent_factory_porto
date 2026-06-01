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
    import { useMaterials } from '../../hooks/useMaterials';
    import LoadingSpinner from '../common/LoadingSpinner';
    import ErrorMessage from '../common/ErrorMessage';
    import { Material } from '../../services/materialService';
    import { MATERIAL_STATUS } from '../../config/constants';

    const MaterialList: React.FC = () => {
      const { materials, loading, error, pagination, loadMaterials, deleteExistingMaterial } = useMaterials();

      const handlePageChange = (event: React.ChangeEvent<unknown>, page: number) => {
        loadMaterials(page - 1, pagination.pageSize); // page is 1-based, API expects 0-based
      };

      const handleDelete = (id: number) => {
        if (window.confirm('Are you sure you want to delete this material?')) {
          deleteExistingMaterial(id).catch(err => console.error("Deletion failed:", err));
        }
      };

      const getStatusColor = (status: string | undefined) => {
        switch (status) {
          case MATERIAL_STATUS.AVAILABLE:
            return 'success';
          case MATERIAL_STATUS.LOW_STOCK:
            return 'warning';
          case MATERIAL_STATUS.OUT_OF_STOCK:
            return 'error';
          default:
            return 'default';
        }
      };

      if (loading && materials.length === 0) {
        return <LoadingSpinner />;
      }

      if (error) {
        return <ErrorMessage message={error} />;
      }

      return (
        <Box sx={{ mt: 4 }}>
          <Typography variant="h4" gutterBottom>
            Materials
          </Typography>
          <Box sx={{ mb: 2, textAlign: 'right' }}>
            <Button variant="contained" color="primary">
              Add New Material
            </Button>
          </Box>
          <TableContainer component={Paper}>
            <Table sx={{ minWidth: 650 }} aria-label="simple table">
              <TableHead>
                <TableRow>
                  <TableCell>ID</TableCell>
                  <TableCell>Name</TableCell>
                  <TableCell>Description</TableCell>
                  <TableCell>Stock Quantity</TableCell>
                  <TableCell>Unit</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {materials.map((material: Material) => (
                  <TableRow key={material.materialId}>
                    <TableCell>{material.materialId || '-'}</TableCell>
                    <TableCell>{material.name}</TableCell>
                    <TableCell>{material.description || '-'}</TableCell>
                    <TableCell>{material.stockQuantity}</TableCell>
                    <TableCell>{material.unit}</TableCell>
                    <TableCell>
                      <Chip label={material.status || 'UNKNOWN'} color={getStatusColor(material.status)} />
                    </TableCell>
                    <TableCell>
                      <Button variant="contained" color="primary" sx={{ mr: 1 }}>
                        Edit
                      </Button>
                      <Button variant="contained" color="error" onClick={() => handleDelete(material.materialId!)}>
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

    export default MaterialList;