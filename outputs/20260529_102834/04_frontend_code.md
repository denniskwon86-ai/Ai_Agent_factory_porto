프론트엔드 엔지니어로서, 제공된 `Tech Spec Summary`와 기존 코드 스니펫을 바탕으로 웹 클라이언트 애플리케이션을 구현하겠습니다. 이전 빌드 오류 피드백 중 Python Pip Install Error는 프론트엔드 개발 범위 밖의 문제이므로, Node.js npm run build Error에 집중하여 코드를 검토하고 누락된 부분을 보완하겠습니다. Node.js 빌드 에러 로그는 특정 오류 메시지 없이 이전 출력만 제공되었으므로, 기존 코드가 문법적으로는 큰 문제가 없다고 판단하고, 전체 애플리케이션 구조를 완성하고 필요한 컴포넌트 및 서비스 레이어를 구현하여 빌드 및 실행이 가능하도록 하겠습니다.

특히, 환경 변수 사용, 커스텀 훅을 통한 상태 관리 로직 분리, 단일 책임 원칙에 따른 컴포넌트 분리 원칙을 엄격히 준수합니다.

---

# 1. 환경 변수 및 글로벌 설정 (.env / config)

<file path=".env.development">
# Frontend API Base URL for development
REACT_APP_API_URL=http://localhost:3001/api
</file>

<file path=".env.production">
# Frontend API Base URL for production
# This should point to your deployed backend or Electron's IPC
REACT_APP_API_URL=http://localhost:3001/api
</file>

<file path="tailwind.config.js">
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
</file>

<file path="postcss.config.js">
module.exports = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
</file>

<file path="src/index.css">
@tailwind base;
@tailwind components;
@tailwind utilities;

body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen',
    'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue',
    sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  background-color: #f4f7f6; /* Light background for the app */
}

code {
  font-family: source-code-pro, Menlo, Monaco, Consolas, 'Courier New',
    monospace;
}
</file>

<file path="src/App.tsx">
// src/App.tsx
import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import SessionsPage from './pages/SessionsPage';

const App: React.FC = () => {
  return (
    <Router>
      <div className="min-h-screen bg-gray-100">
        <Routes>
          <Route path="/" element={<SessionsPage />} />
          {/* Add other routes here if needed */}
        </Routes>
      </div>
    </Router>
  );
};

export default App;
</file>

<file path="src/index.tsx">
// src/index.tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';
import reportWebVitals from './reportWebVitals';

const root = ReactDOM.createRoot(
  document.getElementById('root') as HTMLElement
);
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

// If you want to start measuring performance in your app, pass a function
// to log results (for example: reportWebVitals(console.log))
// or send to an analytics endpoint. Learn more: https://bit.ly/CRA-vitals
reportWebVitals();
</file>

<file path="tsconfig.json">
{
  "compilerOptions": {
    "target": "es5",
    "lib": [
      "dom",
      "dom.iterable",
      "esnext"
    ],
    "allowJs": true,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "forceConsistentCasingInFileNames": true,
    "noFallthroughCasesInSwitch": true,
    "module": "esnext",
    "moduleResolution": "node",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx"
  },
  "include": [
    "src"
  ]
}
</file>

# 2. API 통신 및 데이터 패칭 모듈 (Services)

<file path="src/types.ts">
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
</file>

<file path="src/services/api.ts">
// src/services/api.ts
import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:3001/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    // Centralized error handling
    if (error.response) {
      // The request was made and the server responded with a status code
      // that falls out of the range of 2xx
      console.error('API Error Response:', error.response.data);
      console.error('API Error Status:', error.response.status);
      console.error('API Error Headers:', error.response.headers);
      return Promise.reject(error.response.data.message || 'An unexpected error occurred.');
    } else if (error.request) {
      // The request was made but no response was received
      console.error('API Error Request:', error.request);
      return Promise.reject('No response received from server. Please check your network connection.');
    } else {
      // Something happened in setting up the request that triggered an Error
      console.error('API Error Message:', error.message);
      return Promise.reject('Error setting up API request: ' + error.message);
    }
  }
);

export default api;
</file>

<file path="src/services/sessionService.ts">
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
</file>

<file path="src/hooks/useSessions.ts">
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
</file>

<file path="src/hooks/useSessionDetails.ts">
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
</file>

# 3. UI 컴포넌트 및 페이지 코드 (Components / Pages)

<file path="src/components/common/Button.tsx">
// src/components/common/Button.tsx
import React from 'react';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'outline';
  size?: 'sm' | 'md' | 'lg';
  children: React.ReactNode;
}

const Button: React.FC<ButtonProps> = ({
  variant = 'primary',
  size = 'md',
  children,
  className = '',
  ...props
}) => {
  const baseStyles = 'font-medium rounded-md transition duration-150 ease-in-out focus:outline-none focus:ring-2 focus:ring-offset-2';

  const variantStyles = {
    primary: 'bg-indigo-600 hover:bg-indigo-700 text-white focus:ring-indigo-500',
    secondary: 'bg-gray-200 hover:bg-gray-300 text-gray-800 focus:ring-gray-500',
    danger: 'bg-red-600 hover:bg-red-700 text-white focus:ring-red-500',
    outline: 'border border-gray-300 text-gray-700 hover:bg-gray-50 focus:ring-gray-500',
  };

  const sizeStyles = {
    sm: 'px-3 py-1.5 text-sm',
    md: 'px-4 py-2 text-base',
    lg: 'px-5 py-2.5 text-lg',
  };

  return (
    <button
      className={`${baseStyles} ${variantStyles[variant]} ${sizeStyles[size]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
};

export default Button;
</file>

<file path="src/components/common/Modal.tsx">
// src/components/common/Modal.tsx
import React from 'react';
import ReactDOM from 'react-dom';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}

const Modal: React.FC<ModalProps> = ({ isOpen, onClose, title, children }) => {
  if (!isOpen) return null;

  return ReactDOM.createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center overflow-x-hidden overflow-y-auto outline-none focus:outline-none">
      <div className="fixed inset-0 bg-gray-900 bg-opacity-50" onClick={onClose}></div>
      <div className="relative w-auto max-w-lg mx-auto my-6">
        {/* Modal content */}
        <div className="relative flex flex-col w-full bg-white border-0 rounded-lg shadow-lg outline-none focus:outline-none">
          {/* Header */}
          <div className="flex items-start justify-between p-5 border-b border-solid border-gray-200 rounded-t">
            <h3 className="text-2xl font-semibold text-gray-800">
              {title}
            </h3>
            <button
              className="p-1 ml-auto bg-transparent border-0 text-gray-600 float-right text-3xl leading-none font-semibold outline-none focus:outline-none"
              onClick={onClose}
            >
              <span className="text-gray-600 h-6 w-6 text-2xl block outline-none focus:outline-none">
                ×
              </span>
            </button>
          </div>
          {/* Body */}
          <div className="relative p-6 flex-auto">
            {children}
          </div>
        </div>
      </div>
    </div>,
    document.body // Render modal outside the root app element
  );
};

export default Modal;
</file>

<file path="src/components/common/LoadingSpinner.tsx">
// src/components/common/LoadingSpinner.tsx
import React from 'react';

const LoadingSpinner: React.FC = () => {
  return (
    <div className="flex justify-center items-center">
      <div
        className="animate-spin inline-block w-8 h-8 border-4 rounded-full border-t-indigo-600 border-gray-200"
        role="status"
      >
        <span className="sr-only">Loading...</span>
      </div>
    </div>
  );
};

export default LoadingSpinner;
</file>

<file path="src/components/SessionListItem.tsx">
// src/components/SessionListItem.tsx
import React from 'react';
import { Session } from '../types';
import Button from './common/Button';

interface SessionListItemProps {
  session: Session;
  onSelect: (sessionId: number) => void;
  onEdit: (sessionId: number) => void;
  onDelete: (sessionId: number) => void;
  isSelected: boolean;
}

const SessionListItem: React.FC<SessionListItemProps> = ({
  session,
  onSelect,
  onEdit,
  onDelete,
  isSelected,
}) => {
  const itemClasses = `
    p-4 rounded-lg shadow-sm cursor-pointer transition-all duration-200 ease-in-out
    ${isSelected ? 'bg-indigo-100 border-indigo-500 border-l-4' : 'bg-white hover:bg-gray-50 border border-gray-200'}
  `;

  return (
    <li className={itemClasses}>
      <div className="flex justify-between items-center" onClick={() => onSelect(session.session_id)}>
        <div>
          <h3 className="text-lg font-semibold text-gray-800">{session.name}</h3>
          <p className="text-sm text-gray-500 truncate">{session.storage_path}</p>
        </div>
        <div className="flex space-x-2">
          <Button variant="secondary" size="sm" onClick={(e) => { e.stopPropagation(); onEdit(session.session_id); }}>
            Edit
          </Button>
          <Button variant="danger" size="sm" onClick={(e) => { e.stopPropagation(); onDelete(session.session_id); }}>
            Delete
          </Button>
        </div>
      </div>
    </li>
  );
};

export default SessionListItem;
</file>

<file path="src/components/SessionForm.tsx">
// src/components/SessionForm.tsx
import React, { useState, useEffect } from 'react';
import { CreateSessionPayload, UpdateSessionPayload } from '../types';
import Button from './common/Button';

interface SessionFormProps {
  initialData?: CreateSessionPayload;
  onSubmit: (data: CreateSessionPayload | UpdateSessionPayload) => void;
  isEditing: boolean;
  onCancel: () => void;
}

const SessionForm: React.FC<SessionFormProps> = ({ initialData, onSubmit, isEditing, onCancel }) => {
  const [name, setName] = useState(initialData?.name || '');
  const [storagePath, setStoragePath] = useState(initialData?.storage_path || '');
  const [compression, setCompression] = useState(initialData?.compression || false);
  const [encryption, setEncryption] = useState(initialData?.encryption || false);
  const [errors, setErrors] = useState<{ [key: string]: string }>({});

  useEffect(() => {
    if (initialData) {
      setName(initialData.name);
      setStoragePath(initialData.storage_path);
      setCompression(initialData.compression);
      setEncryption(initialData.encryption);
    } else {
      setName('');
      setStoragePath('');
      setCompression(false);
      setEncryption(false);
    }
    setErrors({}); // Clear errors on initialData change
  }, [initialData]);

  const validate = () => {
    const newErrors: { [key: string]: string } = {};
    if (!name.trim()) newErrors.name = 'Session name is required.';
    if (!storagePath.trim()) newErrors.storagePath = 'Storage path is required.';
    // Add more validation rules as needed
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) {
      return;
    }

    const payload: CreateSessionPayload | UpdateSessionPayload = {
      name,
      storage_path: storagePath,
      compression,
      encryption,
    };
    onSubmit(payload);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label htmlFor="name" className="block text-sm font-medium text-gray-700">Session Name</label>
        <input
          type="text"
          id="name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
          placeholder="e.g., My Important Project Backup"
        />
        {errors.name && <p className="mt-1 text-sm text-red-600">{errors.name}</p>}
      </div>
      <div>
        <label htmlFor="storagePath" className="block text-sm font-medium text-gray-700">Storage Path</label>
        <input
          type="text"
          id="storagePath"
          value={storagePath}
          onChange={(e) => setStoragePath(e.target.value)}
          className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
          placeholder="e.g., /path/to/my/backup/folder"
        />
        {errors.storagePath && <p className="mt-1 text-sm text-red-600">{errors.storagePath}</p>}
      </div>
      <div className="flex items-center">
        <input
          type="checkbox"
          id="compression"
          checked={compression}
          onChange={(e) => setCompression(e.target.checked)}
          className="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 rounded"
        />
        <label htmlFor="compression" className="ml-2 block text-sm text-gray-900">Enable Compression</label>
      </div>
      <div className="flex items-center">
        <input
          type="checkbox"
          id="encryption"
          checked={encryption}
          onChange={(e) => setEncryption(e.target.checked)}
          className="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 rounded"
        />
        <label htmlFor="encryption" className="ml-2 block text-sm text-gray-900">Enable Encryption</label>
      </div>
      <div className="flex justify-end space-x-3 mt-6">
        <Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button>
        <Button type="submit" variant="primary">
          {isEditing ? 'Update Session' : 'Create Session'}
        </Button>
      </div>
    </form>
  );
};

export default SessionForm;
</file>

<file path="src/components/SessionItemsList.tsx">
// src/components/SessionItemsList.tsx
import React from 'react';
import { SessionItem } from '../types';
import LoadingSpinner from './common/LoadingSpinner';

interface SessionItemsListProps {
  items: SessionItem[];
  loading: boolean;
  error: string | null;
}

const SessionItemsList: React.FC<SessionItemsListProps> = ({ items, loading, error }) => {
  if (loading) {
    return <LoadingSpinner />;
  }

  if (error) {
    return <p className="text-red-500">Error loading items: {error}</p>;
  }

  return (
    <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-100">
      <h3 className="text-xl font-semibold mb-3 text-gray-700">Included Items</h3>
      {items.length === 0 ? (
        <p className="text-gray-500">No items configured for this session.</p>
      ) : (
        <ul className="space-y-2 text-gray-600 max-h-60 overflow-y-auto">
          {items.map((item) => (
            <li key={item.session_item_id} className="flex items-center space-x-2">
              <span className="text-indigo-500">
                {item.item_type === 'directory' ? '📁' : '📄'}
              </span>
              <span className="truncate">{item.item_path}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

export default SessionItemsList;
</file>

<file path="src/components/RecoveryLogsList.tsx">
// src/components/RecoveryLogsList.tsx
import React from 'react';
import { RecoveryLog } from '../types';
import LoadingSpinner from './common/LoadingSpinner';

interface RecoveryLogsListProps {
  logs: RecoveryLog[];
  loading: boolean;
  error: string | null;
}

const RecoveryLogsList: React.FC<RecoveryLogsListProps> = ({ logs, loading, error }) => {
  if (loading) {
    return <LoadingSpinner />;
  }

  if (error) {
    return <p className="text-red-500">Error loading logs: {error}</p>;
  }

  const getStatusColor = (status: RecoveryLog['status']) => {
    switch (status) {
      case 'completed': return 'text-green-600';
      case 'failed': return 'text-red-600';
      case 'in_progress': return 'text-blue-600';
      case 'pending': return 'text-yellow-600';
      default: return 'text-gray-600';
    }
  };

  return (
    <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-100">
      <h3 className="text-xl font-semibold mb-3 text-gray-700">Recovery Logs</h3>
      {logs.length === 0 ? (
        <p className="text-gray-500">No recovery logs found for this session.</p>
      ) : (
        <ul className="space-y-3 text-gray-600 max-h-60 overflow-y-auto">
          {logs.map((log) => (
            <li key={log.log_id} className="p-2 border border-gray-100 rounded-md bg-gray-50">
              <div className="flex justify-between items-center text-sm">
                <span className="font-medium">{log.action_type === 'backup' ? 'Backup' : 'Restore'}</span>
                <span className={`${getStatusColor(log.status)} font-semibold`}>
                  {log.status.replace(/_/g, ' ').toUpperCase()}
                </span>
              </div>
              <p className="text-xs text-gray-500 mt-1">
                Path: <span className="font-mono">{log.item_path || 'N/A'}</span>
              </p>
              <p className="text-xs text-gray-500">
                Started: {new Date(log.started_at).toLocaleString()}
              </p>
              {log.completed_at && (
                <p className="text-xs text-gray-500">
                  Completed: {new Date(log.completed_at).toLocaleString()}
                </p>
              )}
              {log.error_message && (
                <p className="text-xs text-red-500">Error: {log.error_message}</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

export default RecoveryLogsList;
</file>

<file path="src/components/SessionDetailView.tsx">
// src/components/SessionDetailView.tsx
import React from 'react';
import { Session, SessionItem, RecoveryLog } from '../types';
import Button from './common/Button';
import LoadingSpinner from './common/LoadingSpinner';
import { useSessionDetails } from '../hooks/useSessionDetails';
import SessionItemsList from './SessionItemsList';
import RecoveryLogsList from './RecoveryLogsList';

interface SessionDetailViewProps {
  sessionId: number | null;
  onBack: () => void;
  onEditSession: (sessionId: number) => void;
}

const SessionDetailView: React.FC<SessionDetailViewProps> = ({ sessionId, onBack, onEditSession }) => {
  const { session, items, logs, loading, error, startSessionBackup, startSessionRestore } = useSessionDetails(sessionId);

  if (!sessionId) {
    return (
      <div className="p-6 bg-white rounded-lg shadow-md flex items-center justify-center h-full text-gray-500">
        <p>Select a session from the left to view details.</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="p-6 bg-white rounded-lg shadow-md flex items-center justify-center h-full">
        <LoadingSpinner />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 bg-white rounded-lg shadow-md flex items-center justify-center h-full text-red-500">
        <p>Error loading session details: {error}</p>
      </div>
    );
  }

  if (!session) {
    return (
      <div className="p-6 bg-white rounded-lg shadow-md flex items-center justify-center h-full text-gray-500">
        <p>Session not found.</p>
      </div>
    );
  }

  return (
    <div className="p-6 bg-white rounded-lg shadow-md flex flex-col h-full">
      <div className="flex justify-between items-center mb-6 pb-4 border-b border-gray-200">
        <h2 className="text-3xl font-bold text-gray-800">{session.name}</h2>
        <div className="flex space-x-3">
          <Button variant="secondary" onClick={() => onEditSession(session.session_id)}>Edit Session</Button>
          <Button variant="outline" onClick={onBack}>Back to List</Button>
        </div>
      </div>

      <div className="flex-grow overflow-y-auto pr-4 -mr-4"> {/* Added overflow-y-auto for scrollable content */}
        <div className="mb-6 p-4 bg-gray-50 rounded-md border border-gray-100">
          <h3 className="text-xl font-semibold mb-3 text-gray-700">Session Information</h3>
          <div className="space-y-2 text-gray-600">
            <p><strong>Storage Path:</strong> {session.storage_path}</p>
            <p><strong>Compression:</strong> {session.compression ? 'Enabled' : 'Disabled'}</p>
            <p><strong>Encryption:</strong> {session.encryption ? 'Enabled' : 'Disabled'}</p>
            <p><strong>Created At:</strong> {new Date(session.created_at).toLocaleString()}</p>
            <p><strong>Last Updated:</strong> {new Date(session.updated_at).toLocaleString()}</p>
          </div>
        </div>
        <div className="flex flex-col space-y-6">
          <SessionItemsList items={items} loading={loading} error={error} />
          <RecoveryLogsList logs={logs} loading={loading} error={error} />
        </div>
      </div>

      {/* Add buttons for actions like "Start Backup", "Start Restore" here */}
      <div className="mt-auto pt-4 border-t border-gray-200 flex justify-end space-x-3">
        <Button variant="primary" onClick={startSessionBackup} disabled={loading}>Start Backup</Button>
        <Button variant="secondary" onClick={startSessionRestore} disabled={loading}>Start Restore</Button>
      </div>
    </div>
  );
};

export default SessionDetailView;
</file>

<file path="src/pages/SessionsPage.tsx">
// src/pages/SessionsPage.tsx
import React, { useState } from 'react';
import { useSessions } from '../hooks/useSessions';
import { CreateSessionPayload, UpdateSessionPayload } from '../types';
import SessionListItem from '../components/SessionListItem';
import SessionDetailView from '../components/SessionDetailView';
import SessionForm from '../components/SessionForm';
import Modal from '../components/common/Modal';
import Button from '../components/common/Button';
import LoadingSpinner from '../components/common/LoadingSpinner';

const SessionsPage: React.FC = () => {
  const { sessions, loading, error, fetchSessions, addSession, editSession, removeSession } = useSessions();

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editingSessionId, setEditingSessionId] = useState<number | null>(null);
  const [selectedSessionId, setSelectedSessionId] = useState<number | null>(null);

  const handleCreateSession = async (data: CreateSessionPayload) => {
    const newSession = await addSession(data);
    if (newSession) {
      setIsModalOpen(false);
      setIsEditing(false);
      setEditingSessionId(null);
      // fetchSessions(); // useSessions hook already updates its state, no need to re-fetch all
    }
  };

  const handleUpdateSession = async (data: UpdateSessionPayload) => {
    if (editingSessionId === null) return;
    const updatedSession = await editSession(editingSessionId, data);
    if (updatedSession) {
      setIsModalOpen(false);
      setIsEditing(false);
      setEditingSessionId(null);
      // useSessions hook already updates its state.
      // If the currently selected session was updated, re-select it to refresh details
      if (selectedSessionId === editingSessionId) {
        // Deselect and re-select to force re-render of SessionDetailView with fresh data
        setSelectedSessionId(null);
        setTimeout(() => setSelectedSessionId(editingSessionId), 0);
      }
    }
  };

  const handleDeleteSession = async (sessionId: number) => {
    if (window.confirm('Are you sure you want to delete this session? This action cannot be undone.')) {
      await removeSession(sessionId);
      // The `removeSession` hook already updates the `sessions` state.
      // We only need to handle deselection if the deleted session was selected.
      if (!error) { // Only deselect if deletion was successful (error is from the hook)
        if (selectedSessionId === sessionId) {
          setSelectedSessionId(null); // Deselect if the deleted session was selected
        }
      }
    }
  };

  const handleEditClick = (sessionId: number) => {
    setEditingSessionId(sessionId);
    setIsEditing(true);
    setIsModalOpen(true);
  };

  const handleAddClick = () => {
    setIsEditing(false);
    setEditingSessionId(null);
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setIsEditing(false);
    setEditingSessionId(null);
  };

  const handleSessionSelect = (sessionId: number) => {
    setSelectedSessionId(sessionId);
  };

  const currentSessionToEdit = editingSessionId ? sessions.find(s => s.session_id === editingSessionId) : undefined;

  return (
    <div className="container mx-auto p-4">
      <h1 className="text-3xl font-bold mb-6 text-gray-800">Sessions Management</h1>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-2xl font-semibold text-gray-700">My Sessions</h2>
            <Button onClick={handleAddClick}>+ New Session</Button>
          </div>
          {loading && <LoadingSpinner />}
          {error && <p className="text-red-500">Error: {error}</p>}
          {!loading && !error && sessions.length === 0 && (
            <p className="text-gray-500">No sessions created yet. Click '+ New Session' to get started.</p>
          )}
          {!loading && !error && sessions.length > 0 && (
            <ul className="space-y-2">
              {sessions.map((session) => (
                <SessionListItem
                  key={session.session_id}
                  session={session}
                  onSelect={handleSessionSelect}
                  onEdit={handleEditClick}
                  onDelete={handleDeleteSession}
                  isSelected={selectedSessionId === session.session_id}
                />
              ))}
            </ul>
          )}
        </div>

        <div className="lg:col-span-2">
          <SessionDetailView
            sessionId={selectedSessionId}
            onBack={() => setSelectedSessionId(null)}
            onEditSession={handleEditClick}
          />
        </div>
      </div>

      <Modal isOpen={isModalOpen} onClose={handleCloseModal} title={isEditing ? 'Edit Session' : 'Create New Session'}>
        <SessionForm
          initialData={isEditing && currentSessionToEdit ? {
            name: currentSessionToEdit.name,
            storage_path: currentSessionToEdit.storage_path,
            compression: currentSessionToEdit.compression,
            encryption: currentSessionToEdit.encryption,
          } : undefined}
          onSubmit={isEditing ? handleUpdateSession : handleCreateSession}
          isEditing={isEditing}
          onCancel={handleCloseModal}
        />
      </Modal>
    </div>
  );
};

export default SessionsPage;
</file>

<file path="package.json">
{
  "name": "electron-react-app",
  "version": "0.1.0",
  "private": true,
  "main": "electron/main.js",
  "homepage": "./",
  "scripts": {
    "start": "react-scripts start",
    "build": "react-scripts build",
    "test": "react-scripts test",
    "eject": "react-scripts eject",
    "electron:dev": "concurrently \"npm start\" \"wait-on http://localhost:3000 && electron .\"",
    "electron:build": "npm run build && electron-builder"
  },
  "dependencies": {
    "axios": "^1.6.8",
    "concurrently": "^8.2.2",
    "dotenv": "^16.4.5",
    "electron": "^29.1.6",
    "electron-builder": "^24.13.0",
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.22.3",
    "react-scripts": "5.0.1",
    "wait-on": "^7.2.0",
    "web-vitals": "^3.1.1"
  },
  "devDependencies": {
    "@types/node": "^20.12.7",
    "@types/react": "^18.2.79",
    "@types/react-dom": "^18.2.25",
    "tailwindcss": "^3.4.3",
    "typescript": "^4.9.5",
    "postcss": "^8.4.38",
    "autoprefixer": "^10.4.19"
  },
  "eslintConfig": {
    "extends": [
      "react-app",
      "react-app/jest"
    ]
  },
  "browserslist": {
    "production": [
      ">0.2%",
      "not dead",
      "not op_mini all"
    ],
    "development": [
      "last 1 chrome version",
      "last 1 firefox version",
      "last 1 safari version"
    ]
  },
  "build": {
    "appId": "com.example.electron-react-app",
    "productName": "ElectronReactApp",
    "files": [
      "build/**/*",
      "electron/main.js",
      "electron/preload.js"
    ],
    "directories": {
      "buildResources": "assets"
    }
  }
}
</file>

<file path="electron/main.js">
// electron/main.js
const { app, BrowserWindow } = require('electron');
const path = require('path');
const isDev = require('electron-is-dev');

function createWindow() {
  const win = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false, // It's safer to keep nodeIntegration false and use preload script
      contextIsolation: true, // Recommended for security
    },
  });

  // Load the React app
  win.loadURL(
    isDev
      ? 'http://localhost:3000'
      : `file://${path.join(__dirname, '../build/index.html')}`
  );

  // Open the DevTools.
  if (isDev) {
    win.webContents.openDevTools();
  }
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});
</file>

<file path="electron/preload.js">
// electron/preload.js
// All of the Node.js APIs are available in the preload process.
// It has the same sandbox as a Chrome extension.
const { contextBridge, ipcRenderer } = require('electron');

// Expose some APIs to the renderer process
contextBridge.exposeInMainWorld('electron', {
  // Example: a function to send a message to the main process
  sendMessage: (channel, data) => {
    ipcRenderer.send(channel, data);
  },
  // Example: a function to receive a message from the main process
  onMessage: (channel, callback) => {
    ipcRenderer.on(channel, (event, ...args) => callback(...args));
  },
  // You can expose other Electron APIs here if needed, but be cautious about security.
});
</file>