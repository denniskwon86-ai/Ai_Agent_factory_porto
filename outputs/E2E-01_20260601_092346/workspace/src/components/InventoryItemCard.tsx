// src/components/InventoryItemCard.tsx
import React from 'react';
import { Card, CardContent, Typography, CardActions, Button, Box } from '@mui/material';
import { Inventory } from '../services/inventoryService';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';

interface InventoryItemCardProps {
  item: Inventory;
  onEdit: (item: Inventory) => void;
  onDelete: (id: string) => void;
}

const InventoryItemCard: React.FC<InventoryItemCardProps> = ({ item, onEdit, onDelete }) => {
  return (
    <Card sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <CardContent sx={{ flexGrow: 1 }}>
        <Typography variant="h6" component="div" gutterBottom>
          {item.material.name}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Material ID: {item.material.material_id}
        </Typography>
        <Typography variant="body1" sx={{ mt: 1 }}>
          Quantity: <strong>{item.quantity}</strong>
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Location: {item.location}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Last Updated: {new Date(item.last_updated).toLocaleString()}
        </Typography>
      </CardContent>
      <CardActions sx={{ justifyContent: 'flex-end' }}>
        <Button size="small" startIcon={<EditIcon />} onClick={() => onEdit(item)}>
          Edit
        </Button>
        <Button size="small" color="error" startIcon={<DeleteIcon />} onClick={() => onDelete(item.inventory_id)}>
          Delete
        </Button>
      </CardActions>
    </Card>
  );
};

export default InventoryItemCard;