import { useState, useEffect, useCallback } from 'react';
import { apiService } from '../services/api';

interface RecoveryLog {
  log_id: number;
  session_id: number;
  item_path: string;
  action_type: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  error_message: string | null;
}

interface UseRecoveryLogsResult {
  logs: RecoveryLog[];
  loading: boolean;
  error: string | null;
  fetchLogs: (sessionId: number) => Promise<void>;
  addLog: (sessionId: number, logData: Omit<RecoveryLog, 'log_id' | 'completed_at' | 'error_message'>) => Promise<void>;
  updateLog: (logId: number, logData: Partial<Omit<RecoveryLog, 'log_id' | 'session_id' | 'item_path' | 'action_type' | 'started_at'>>) => Promise<void>;
}

const useRecoveryLogs = (sessionId: number | null): UseRecoveryLogsResult => {
  const [logs, setLogs] = useState<RecoveryLog[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const fetchLogs = useCallback(async (currentSessionId: number) => {
    if (!currentSessionId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await apiService.getRecoveryLogs(currentSessionId);
      setLogs(data);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch recovery logs');
    } finally {
      setLoading(false);
    }
  }, []);

  const addLog = useCallback(async (currentSessionId: number, logData: Omit<RecoveryLog, 'log_id' | 'completed_at' | 'error_message'>) => {
    if (!currentSessionId) return;
    setLoading(true);
    setError(null);
    try {
      await apiService.addRecoveryLog(currentSessionId, logData);
      await fetchLogs(currentSessionId); // Refresh the list
    } catch (err: any) {
      setError(err.message || 'Failed to add recovery log');
      throw err;
    } finally {
      setLoading(false);
    }
  }, [fetchLogs]);

  const updateLog = useCallback(async (logId: number, logData: Partial<Omit<RecoveryLog, 'log_id' | 'session_id' | 'item_path' | 'action_type' | 'started_at'>>) => {
    setLoading(true);
    setError(null);
    try {
      await apiService.updateRecoveryLog(logId, logData);
      await fetchLogs(logs.find(log => log.log_id === logId)?.session_id || 0); // Refresh logs for the relevant session
    } catch (err: any) {
      setError(err.message || 'Failed to update recovery log');
      throw err;
    } finally {
      setLoading(false);
    }
  }, [logs]); // logs dependency to find the session_id

  useEffect(() => {
    if (sessionId !== null) {
      fetchLogs(sessionId);
    } else {
      setLogs([]); // Clear logs if no session is selected
    }
  }, [sessionId, fetchLogs]);

  return {
    logs,
    loading,
    error,
    fetchLogs,
    addLog,
    updateLog,
  };
};

export default useRecoveryLogs;