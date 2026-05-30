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