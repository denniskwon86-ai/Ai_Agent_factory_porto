// src/services/recoveryLogService.ts
import api from './api';
import { RecoveryLog } from '../types';

export const getRecoveryLogsBySessionId = async (sessionId: number): Promise<RecoveryLog[]> => {
  try {
    const response = await api.get<RecoveryLog[]>(`/sessions/${sessionId}/logs`);
    return response.data;
  } catch (error) {
    console.error(`Error fetching recovery logs for session ID ${sessionId}:`, error);
    throw error;
  }
};

// Additional services for recovery logs can be added here if needed.