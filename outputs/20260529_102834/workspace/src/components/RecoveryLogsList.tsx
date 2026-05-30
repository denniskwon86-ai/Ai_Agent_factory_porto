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