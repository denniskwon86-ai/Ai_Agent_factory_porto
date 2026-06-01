// src/components/InventoryList.tsx
import React from 'react';
import { Grid, Typography, Box } from '@mui/material';
import InventoryItemCard from './InventoryItemCard';
import { Inventory } from '../services/inventoryService';

interface InventoryListProps {
  inventoryItems: Inventory[];
  onEdit: (item: Inventory) => void;
  onDelete: (id: string) => void;
}

const InventoryList: React.FC<InventoryListProps> = ({ inventoryItems, onEdit, onDelete }) => {
  if (inventoryItems.length === 0) {
    return (
      <Box sx={{ mt: 4, textAlign: 'center' }}>
        <Typography variant="h6" color="text.secondary">
          No inventory items found.
        </Typography>
      </Box>
    );
  }

  return (
    <Grid container spacing={3}>
      {inventoryItems.map((item) => (
        <Grid item xs={12} sm={6} md={4} key={item.inventory_id}>
          <InventoryItemCard
            item={item}
            onEdit={onEdit}
            onDelete={onDelete}
          />
        </Grid>
      ))}
    </Grid>
  );
};

export default InventoryList;