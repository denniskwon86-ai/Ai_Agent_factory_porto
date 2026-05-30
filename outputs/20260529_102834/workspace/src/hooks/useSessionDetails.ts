// src/hooks/useSessionDetails.ts
import { useState, useEffect, useCallback } from 'react';
import { sessionService } from '../services/sessionService';
import { Session, SessionItem, RecoveryLog } from '../types';

export const useSessionDetails = (sessionId: number | null) => {
  const [session, setSession] = useState<Session | null>(null);
  const [items, setItems] = useState<SessionItem[]>([]);
  const [logs, setLogs] = useState<RecoveryLog[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSessionDetails = useCallback(async (id: number) => {
    setLoading(true);
    setError(null);
    try {
      const [sessionData, itemsData, logsData] = await Promise.all([
        sessionService.getSessionById(id),
        sessionService.getSessionItems(id),
        sessionService.getRecoveryLogs(id),
      ]);
      setSession(sessionData);
      setItems(itemsData);
      setLogs(logsData);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch session details.');
      console.error('Error fetching session details:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (sessionId) {
      fetchSessionDetails(sessionId);
    } else {
      setSession(null);
      setItems([]);
      setLogs([]);
      setLoading(false);
      setError(null);
    }
  }, [sessionId, fetchSessionDetails]);

  const startSessionBackup = useCallback(async () => {
    if (!sessionId) return;
    try {
      const newLog = await sessionService.startBackup(sessionId);
      setLogs((prev) => [...prev, newLog]);
      // Optionally re-fetch logs to get updated status
      fetchSessionDetails(sessionId);
    } catch (err: any) {
      setError(err.message || 'Failed to start backup.');
      console.error('Error starting backup:', err);
    }
  }, [sessionId, fetchSessionDetails]);

  const startSessionRestore = useCallback(async () => {
    if (!sessionId) return;
    try {
      const newLog = await sessionService.startRestore(sessionId);
      setLogs((prev) => [...prev, newLog]);
      // Optionally re-fetch logs to get updated status
      fetchSessionDetails(sessionId);
    } catch (err: any) {
      setError(err.message || 'Failed to start restore.');
      console.error('Error starting restore:', err);
    }
  }, [sessionId, fetchSessionDetails]);

  return {
    session,
    items,
    logs,
    loading,
    error,
    fetchSessionDetails,
    startSessionBackup,
    startSessionRestore,
  };
};