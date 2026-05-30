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