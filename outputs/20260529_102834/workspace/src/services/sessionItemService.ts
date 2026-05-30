// src/services/sessionItemService.ts
import api from './api';
import { SessionItem } from '../types';

export const getSessionItemsBySessionId = async (sessionId: number): Promise<SessionItem[]> => {
  try {
    const response = await api.get<SessionItem[]>(`/sessions/${sessionId}/items`);
    return response.data;
  } catch (error) {
    console.error(`Error fetching session items for session ID ${sessionId}:`, error);
    throw error;
  }
};

// Additional services for session items (e.g., add, delete) can be added here if needed.