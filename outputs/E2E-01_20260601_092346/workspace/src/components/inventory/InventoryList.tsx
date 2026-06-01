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
    import { useInventory } from '../../hooks/useInventory';
    import LoadingSpinner from '../common/LoadingSpinner';
    import ErrorMessage from '../common/ErrorMessage';
    import { Inventory } from '../../services/inventoryService';
    import { INVENTORY_STATUS } from '../../config/constants';

    const InventoryList: React.FC = () => {
      const { inventories, loading, error, pagination, loadInventories, deleteExistingInventory } = useInventory();

      const handlePageChange = (event: React.ChangeEvent<unknown>, page: number) => {
        loadInventories(page - 1, pagination.pageSize); // page is 1-based, API expects 0-based
      };

      const handleDelete = (id: number) => {
        if (window.confirm('Are you sure you want to delete this inventory record?')) {
          deleteExistingInventory(id).catch(err => console.error("Deletion failed:", err));
        }
      };

      const getStatusColor = (status: string | undefined) => {
        switch (status) {
          case INVENTORY_STATUS.IN_STOCK:
            return 'success';
          case INVENTORY_STATUS.LOW_STOCK:
            return 'warning';
          case INVENTORY_STATUS.OUT_OF_STOCK:
            return 'error';
          default:
            return 'default';
        }
      };

      if (loading && inventories.length === 0) {
        return <LoadingSpinner />;
      }

      if (error) {
        return <ErrorMessage message={error} />;
      }

      return (
        <Box sx={{ mt: 4 }}>
          <Typography variant="h4" gutterBottom>
            Inventory
          </Typography>
          <Box sx={{ mb: 2, textAlign: 'right' }}>
            <Button variant="contained" color="primary">
              Add New Inventory
            </Button>
          </Box>
          <TableContainer component={Paper}>
            <Table sx={{ minWidth: 650 }} aria-label="simple table">
              <TableHead>
                <TableRow>
                  <TableCell>ID</TableCell>
                  <TableCell>Material ID</TableCell>
                  <TableCell>Location</TableCell>
                  <TableCell>Quantity</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {inventories.map((inventory: Inventory) => (
                  <TableRow key={inventory.inventoryId}>
                    <TableCell>{inventory.inventoryId || '-'}</TableCell>
                    <TableCell>{inventory.materialId}</TableCell>
                    <TableCell>{inventory.location || '-'}</TableCell>
                    <TableCell>{inventory.quantity}</TableCell>
                    <TableCell>
                      <Chip label={inventory.status || 'UNKNOWN'} color={getStatusColor(inventory.status)} />
                    </TableCell>
                    <TableCell>
                      <Button variant="contained" color="primary" sx={{ mr: 1 }}>
                        Edit
                      </Button>
                      <Button variant="contained" color="error" onClick={() => handleDelete(inventory.inventoryId!)}>
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

    export default InventoryList;