import { useState, useEffect, useCallback } from 'react';
import { apiService } from '../services/api';

interface SessionItem {
  session_item_id: number;
  session_id: number;
  item_path: string;
  item_type: string; // e.g., 'file', 'directory'
}

interface UseSessionItemsResult {
  items: SessionItem[];
  loading: boolean;
  error: string | null;
  fetchItems: (sessionId: number) => Promise<void>;
  addItem: (sessionId: number, itemData: Omit<SessionItem, 'session_item_id'>) => Promise<void>;
  deleteItem: (sessionId: number, itemId: number) => Promise<void>;
}

const useSessionItems = (sessionId: number | null): UseSessionItemsResult => {
  const [items, setItems] = useState<SessionItem[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const fetchItems = useCallback(async (currentSessionId: number) => {
    if (!currentSessionId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await apiService.getSessionItems(currentSessionId);
      setItems(data);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch session items');
    } finally {
      setLoading(false);
    }
  }, []);

  const addItem = useCallback(async (currentSessionId: number, itemData: Omit<SessionItem, 'session_item_id'>) => {
    if (!currentSessionId) return;
    setLoading(true);
    setError(null);
    try {
      await apiService.addSessionItem(currentSessionId, itemData);
      await fetchItems(currentSessionId); // Refresh the list
    } catch (err: any) {
      setError(err.message || 'Failed to add session item');
      throw err;
    } finally {
      setLoading(false);
    }
  }, [fetchItems]);

  const deleteItem = useCallback(async (currentSessionId: number, itemId: number) => {
    if (!currentSessionId) return;
    setLoading(true);
    setError(null);
    try {
      await apiService.deleteSessionItem(currentSessionId, itemId);
      await fetchItems(currentSessionId); // Refresh the list
    } catch (err: any) {
      setError(err.message || 'Failed to delete session item');
      throw err;
    } finally {
      setLoading(false);
    }
  }, [fetchItems]);

  useEffect(() => {
    if (sessionId !== null) {
      fetchItems(sessionId);
    } else {
      setItems([]); // Clear items if no session is selected
    }
  }, [sessionId, fetchItems]);

  return {
    items,
    loading,
    error,
    fetchItems,
    addItem,
    deleteItem,
  };
};

export default useSessionItems;