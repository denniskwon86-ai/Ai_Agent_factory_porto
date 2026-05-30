// src/services/sessionService.ts
import api from './api';
import { Session, SessionItem, RecoveryLog, CreateSessionPayload, UpdateSessionPayload, ApiResponse } from '../types';

const SESSION_BASE_URL = '/sessions';

export const sessionService = {
  // Fetch all sessions
  getSessions: async (): Promise<Session[]> => {
    const response = await api.get<ApiResponse<Session[]>>(SESSION_BASE_URL);
    return response.data.data;
  },

  // Fetch a single session by ID
  getSessionById: async (id: number): Promise<Session> => {
    const response = await api.get<ApiResponse<Session>>(`${SESSION_BASE_URL}/${id}`);
    return response.data.data;
  },

  // Create a new session
  createSession: async (payload: CreateSessionPayload): Promise<Session> => {
    const response = await api.post<ApiResponse<Session>>(SESSION_BASE_URL, payload);
    return response.data.data;
  },

  // Update an existing session
  updateSession: async (id: number, payload: UpdateSessionPayload): Promise<Session> => {
    const response = await api.put<ApiResponse<Session>>(`${SESSION_BASE_URL}/${id}`, payload);
    return response.data.data;
  },

  // Delete a session
  deleteSession: async (id: number): Promise<void> => {
    await api.delete<ApiResponse<void>>(`${SESSION_BASE_URL}/${id}`);
  },

  // Fetch items for a specific session
  getSessionItems: async (sessionId: number): Promise<SessionItem[]> => {
    const response = await api.get<ApiResponse<SessionItem[]>>(`${SESSION_BASE_URL}/${sessionId}/items`);
    return response.data.data;
  },

  // Fetch recovery logs for a specific session
  getRecoveryLogs: async (sessionId: number): Promise<RecoveryLog[]> => {
    const response = await api.get<ApiResponse<RecoveryLog[]>>(`${SESSION_BASE_URL}/${sessionId}/logs`);
    return response.data.data;
  },

  // Start backup for a session
  startBackup: async (sessionId: number): Promise<RecoveryLog> => {
    const response = await api.post<ApiResponse<RecoveryLog>>(`${SESSION_BASE_URL}/${sessionId}/backup`);
    return response.data.data;
  },

  // Start restore for a session
  startRestore: async (sessionId: number): Promise<RecoveryLog> => {
    const response = await api.post<ApiResponse<RecoveryLog>>(`${SESSION_BASE_URL}/${sessionId}/restore`);
    return response.data.data;
  },
};