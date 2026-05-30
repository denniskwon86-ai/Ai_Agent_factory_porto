import { useState, useEffect, useCallback } from 'react';
import { apiService } from '../services/api';

// Define interfaces for your data models
interface Session {
  session_id: string;
  name: string;
  storage_path: string;
  compression: string;
  encryption: string;
  created_at: string;
  updated_at: string;
}

interface SessionItem {
  session_item_id: string;
  session_id: string;
  item_path: string;
  item_type: string;
}

interface RecoveryLog {
  log_id: string;
  session_id: string;
  item_path: string;
  action_type: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  error_message: string | null;
}

interface UseSessionReturn {
  sessions: Session[];
  sessionItems: SessionItem[];
  recoveryLogs: RecoveryLog[];
  loading: boolean;
  error: string | null;
  fetchSessions: () => Promise<void>;
  fetchSessionItems: (sessionId: string) => Promise<void>;
  fetchRecoveryLogs: (sessionId: string) => Promise<void>;
  createSession: (sessionData: Omit<Session, 'session_id' | 'created_at' | 'updated_at'>) => Promise<Session | null>;
  updateSession: (sessionId: string, sessionData: Partial<Session>) => Promise<Session | null>;
  deleteSession: (sessionId: string) => Promise<boolean>;
  addSessionItem: (sessionId: string, itemData: Omit<SessionItem, 'session_item_id'>) => Promise<SessionItem | null>;
  updateSessionItem: (sessionItemId: string, itemData: Partial<SessionItem>) => Promise<SessionItem | null>;
  deleteSessionItem: (sessionItemId: string) => Promise<boolean>;
  addRecoveryLog: (logData: Omit<RecoveryLog, 'log_id' | 'started_at' | 'completed_at'>) => Promise<RecoveryLog | null>;
  updateRecoveryLog: (logId: string, logData: Partial<RecoveryLog>) => Promise<RecoveryLog | null>;
  deleteRecoveryLog: (logId: string) => Promise<boolean>;
}

const useSession = (): UseSessionReturn => {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [sessionItems, setSessionItems] = useState<SessionItem[]>([]);
  const [recoveryLogs, setRecoveryLogs] = useState<RecoveryLog[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const handleError = useCallback((err: any) => {
    setError(err.message || 'An unexpected error occurred.');
    console.error('Error:', err);
    setLoading(false);
  }, []);

  const fetchSessions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiService.get<Session[]>('/sessions');
      setSessions(data);
    } catch (err) {
      handleError(err);
    } finally {
      setLoading(false);
    }
  }, [handleError]);

  const fetchSessionItems = useCallback(async (sessionId: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiService.get<SessionItem[]>(`/sessions/${sessionId}/items`);
      setSessionItems(data);
    } catch (err) {
      handleError(err);
    } finally {
      setLoading(false);
    }
  }, [handleError]);

  const fetchRecoveryLogs = useCallback(async (sessionId: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiService.get<RecoveryLog[]>(`/sessions/${sessionId}/logs`);
      setRecoveryLogs(data);
    } catch (err) {
      handleError(err);
    } finally {
      setLoading(false);
    }
  }, [handleError]);

  const createSession = useCallback(async (sessionData: Omit<Session, 'session_id' | 'created_at' | 'updated_at'>): Promise<Session | null> => {
    setLoading(true);
    setError(null);
    try {
      const newSession = await apiService.post<Session>('/sessions', sessionData);
      setSessions(prevSessions => [...prevSessions, newSession]);
      return newSession;
    } catch (err) {
      handleError(err);
      return null;
    } finally {
      setLoading(false);
    }
  }, [handleError]);

  const updateSession = useCallback(async (sessionId: string, sessionData: Partial<Session>): Promise<Session | null> => {
    setLoading(true);
    setError(null);
    try {
      const updatedSession = await apiService.put<Session>(`/sessions/${sessionId}`, sessionData);
      setSessions(prevSessions =>
        prevSessions.map(session =>
          session.session_id === sessionId ? updatedSession : session
        )
      );
      return updatedSession;
    } catch (err) {
      handleError(err);
      return null;
    } finally {
      setLoading(false);
    }
  }, [handleError]);

  const deleteSession = useCallback(async (sessionId: string): Promise<boolean> => {
    setLoading(true);
    setError(null);
    try {
      await apiService.delete(`/sessions/${sessionId}`);
      setSessions(prevSessions => prevSessions.filter(session => session.session_id !== sessionId));
      // Also clear related items and logs if they are not managed by backend cascade delete
      setSessionItems(prevItems => prevItems.filter(item => item.session_id !== sessionId));
      setRecoveryLogs(prevLogs => prevLogs.filter(log => log.session_id !== sessionId));
      return true;
    } catch (err) {
      handleError(err);
      return false;
    } finally {
      setLoading(false);
    }
  }, [handleError]);

  const addSessionItem = useCallback(async (sessionId: string, itemData: Omit<SessionItem, 'session_item_id'>): Promise<SessionItem | null> => {
    setLoading(true);
    setError(null);
    try {
      const newItem = await apiService.post<SessionItem>(`/sessions/${sessionId}/items`, itemData);
      setSessionItems(prevItems => [...prevItems, newItem]);
      return newItem;
    } catch (err) {
      handleError(err);
      return null;
    } finally {
      setLoading(false);
    }
  }, [handleError]);

  const updateSessionItem = useCallback(async (sessionItemId: string, itemData: Partial<SessionItem>): Promise<SessionItem | null> => {
    setLoading(true);
    setError(null);
    try {
      const updatedItem = await apiService.put<SessionItem>(`/session-items/${sessionItemId}`, itemData); // Assuming a dedicated endpoint for items
      setSessionItems(prevItems =>
        prevItems.map(item =>
          item.session_item_id === sessionItemId ? updatedItem : item
        )
      );
      return updatedItem;
    } catch (err) {
      handleError(err);
      return null;
    } finally {
      setLoading(false);
    }
  }, [handleError]);

  const deleteSessionItem = useCallback(async (sessionItemId: string): Promise<boolean> => {
    setLoading(true);
    setError(null);
    try {
      await apiService.delete(`/session-items/${sessionItemId}`); // Assuming a dedicated endpoint for items
      setSessionItems(prevItems => prevItems.filter(item => item.session_item_id !== sessionItemId));
      return true;
    } catch (err) {
      handleError(err);
      return false;
    } finally {
      setLoading(false);
    }
  }, [handleError]);

  const addRecoveryLog = useCallback(async (logData: Omit<RecoveryLog, 'log_id' | 'started_at' | 'completed_at'>): Promise<RecoveryLog | null> => {
    setLoading(true);
    setError(null);
    try {
      const newLog = await apiService.post<RecoveryLog>('/recovery-logs', logData);
      setRecoveryLogs(prevLogs => [...prevLogs, newLog]);
      return newLog;
    } catch (err) {
      handleError(err);
      return null;
    } finally {
      setLoading(false);
    }
  }, [handleError]);

  const updateRecoveryLog = useCallback(async (logId: string, logData: Partial<RecoveryLog>): Promise<RecoveryLog | null> => {
    setLoading(true);
    setError(null);
    try {
      const updatedLog = await apiService.put<RecoveryLog>(`/recovery-logs/${logId}`, logData);
      setRecoveryLogs(prevLogs =>
        prevLogs.map(log =>
          log.log_id === logId ? updatedLog : log
        )
      );
      return updatedLog;
    } catch (err) {
      handleError(err);
      return null;
    } finally {
      setLoading(false);
    }
  }, [handleError]);

  const deleteRecoveryLog = useCallback(async (logId: string): Promise<boolean> => {
    setLoading(true);
    setError(null);
    try {
      await apiService.delete(`/recovery-logs/${logId}`);
      setRecoveryLogs(prevLogs => prevLogs.filter(log => log.log_id !== logId));
      return true;
    } catch (err) {
      handleError(err);
      return false;
    } finally {
      setLoading(false);
    }
  }, [handleError]);

  // Initial data fetching can be done here or in components
  // useEffect(() => {
  //   fetchSessions();
  // }, [fetchSessions]);

  return {
    sessions,
    sessionItems,
    recoveryLogs,
    loading,
    error,
    fetchSessions,
    fetchSessionItems,
    fetchRecoveryLogs,
    createSession,
    updateSession,
    deleteSession,
    addSessionItem,
    updateSessionItem,
    deleteSessionItem,
    addRecoveryLog,
    updateRecoveryLog,
    deleteRecoveryLog,
  };
};

export default useSession;