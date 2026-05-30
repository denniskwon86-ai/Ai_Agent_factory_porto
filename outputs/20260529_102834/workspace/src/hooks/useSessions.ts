// src/hooks/useSessions.ts
import { useState, useEffect, useCallback } from 'react';
import { sessionService } from '../services/sessionService';
import { Session, CreateSessionPayload, UpdateSessionPayload } from '../types';

export const useSessions = () => {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSessions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await sessionService.getSessions();
      setSessions(data);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch sessions.');
      console.error('Error fetching sessions:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  const addSession = useCallback(async (payload: CreateSessionPayload): Promise<Session | undefined> => {
    setLoading(true);
    setError(null);
    try {
      const newSession = await sessionService.createSession(payload);
      setSessions((prev) => [...prev, newSession]);
      return newSession;
    } catch (err: any) {
      setError(err.message || 'Failed to create session.');
      console.error('Error creating session:', err);
      return undefined;
    } finally {
      setLoading(false);
    }
  }, []);

  const editSession = useCallback(async (id: number, payload: UpdateSessionPayload): Promise<Session | undefined> => {
    setLoading(true);
    setError(null);
    try {
      const updatedSession = await sessionService.updateSession(id, payload);
      setSessions((prev) => prev.map((s) => (s.session_id === id ? updatedSession : s)));
      return updatedSession;
    } catch (err: any) {
      setError(err.message || 'Failed to update session.');
      console.error('Error updating session:', err);
      return undefined;
    } finally {
      setLoading(false);
    }
  }, []);

  const removeSession = useCallback(async (id: number): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      await sessionService.deleteSession(id);
      setSessions((prev) => prev.filter((s) => s.session_id !== id));
    } catch (err: any) {
      setError(err.message || 'Failed to delete session.');
      console.error('Error deleting session:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  return {
    sessions,
    loading,
    error,
    fetchSessions,
    addSession,
    editSession,
    removeSession,
  };
};