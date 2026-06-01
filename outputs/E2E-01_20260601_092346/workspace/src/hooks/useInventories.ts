import { useEffect } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import { RootState, AppDispatch } from '../store';
import { fetchInventories, fetchInventoryById, addInventory, editInventory, removeInventory, resetInventoryState } from '../store/slices/inventorySlice';
import { Inventory } from '../services/inventoryService';

export const useInventories = () => {
  const dispatch = useDispatch<AppDispatch>();
  const { inventories, currentInventory, loading, error, pagination } = useSelector((state: RootState) => state.inventories);

  useEffect(() => {
    // Fetch initial list of inventories on component mount
    dispatch(fetchInventories({ page: pagination.pageNumber, size: pagination.pageSize }));
  }, [dispatch, pagination.pageNumber, pagination.pageSize]); // Re-fetch if pagination changes

  const loadInventories = (page: number, size: number) => {
    dispatch(fetchInventories({ page, size }));
  };

  const loadInventoryDetails = (id: number) => {
    dispatch(fetchInventoryById(id));
  };

  const createNewInventory = (inventory: Omit<Inventory, 'inventoryId'>) => {
    dispatch(addInventory(inventory));
  };

  const updateExistingInventory = (id: number, inventory: Inventory) => {
    dispatch(editInventory({ id, inventory }));
  };

  const deleteExistingInventory = (id: number) => {
    dispatch(removeInventory(id));
  };

  const resetCurrentInventory = () => {
    dispatch(resetInventoryState());
  };

  return {
    inventories,
    currentInventory,
    loading,
    error,
    pagination,
    loadInventories,
    loadInventoryDetails,
    createNewInventory,
    updateExistingInventory,
    deleteExistingInventory,
    resetCurrentInventory,
  };
};