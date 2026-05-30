// src/types/index.ts

export interface Session {
  session_id: number;
  name: string;
  storage_path: string;
  compression: boolean;
  encryption: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateSessionPayload {
  name: string;
  storage_path: string;
  compression: boolean;
  encryption: boolean;
}

export interface UpdateSessionPayload {
  name?: string;
  storage_path?: string;
  compression?: boolean;
  encryption?: boolean;
}

export interface SessionItem {
  session_item_id: number;
  session_id: number;
  item_path: string;
  item_type: 'file' | 'directory';
}

export type ActionType = 'backup' | 'restore' | 'delete';
export type RecoveryStatus = 'pending' | 'in_progress' | 'completed' | 'failed';

export interface RecoveryLog {
  log_id: number;
  session_id: number;
  item_path: string;
  action_type: ActionType;
  status: RecoveryStatus;
  started_at: string;
  completed_at: string | null;
  error_message: string | null;
}