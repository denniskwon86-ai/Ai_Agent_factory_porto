// src/types.ts

export interface Session {
  session_id: number;
  name: string;
  storage_path: string;
  compression: boolean;
  encryption: boolean;
  created_at: string;
  updated_at: string;
}

export interface SessionItem {
  session_item_id: number;
  session_id: number;
  item_path: string;
  item_type: 'file' | 'directory';
}

export interface RecoveryLog {
  log_id: number;
  session_id: number;
  item_path: string;
  action_type: 'backup' | 'restore';
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  started_at: string;
  completed_at: string | null;
  error_message: string | null;
}

export type CreateSessionPayload = Omit<Session, 'session_id' | 'created_at' | 'updated_at'>;
export type UpdateSessionPayload = Partial<CreateSessionPayload>; // Allow partial updates

export interface ApiResponse<T> {
  data: T;
  message?: string;
  error?: string;
}