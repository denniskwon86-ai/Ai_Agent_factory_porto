// src/hooks/useInventory.ts
import { useEffect } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import { RootState, AppDispatch } from '../store';
import {
  fetchInventoryItems,
  addInventoryItem,
  updateInventoryItem,
  deleteInventoryItem,
} from '../store/slices/inventorySlice';
import { InventoryCreate, InventoryUpdate } from '../services/inventoryService';

export const useInventory = () => {
  const dispatch: AppDispatch = useDispatch();
  const { items, loading, error } = useSelector((state: RootState) => state.inventory);

  useEffect(() => {
    dispatch(fetchInventoryItems());
  }, [dispatch]);

  const createInventory = (newItem: InventoryCreate) => {
    return dispatch(addInventoryItem(newItem)).unwrap();
  };

  const editInventory = (id: string, data: InventoryUpdate) => {
    return dispatch(updateInventoryItem({ id, data })).unwrap();
  };

  const removeInventory = (id: string) => {
    return dispatch(deleteInventoryItem(id)).unwrap();
  };

  const refetchInventory = () => {
    dispatch(fetchInventoryItems());
  };

  return {
    inventoryItems: items,
    loading,
    error,
    createInventory,
    editInventory,
    removeInventory,
    refetchInventory,
  };
};