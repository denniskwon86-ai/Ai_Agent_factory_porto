import React, { useEffect, useState } from 'react';
import useSession from '../hooks/useSession';
import Button from '../components/common/Button';
import Table from '../components/common/Table';
import Input from '../components/common/Input';
import Modal from '../components/common/Modal';

// Define interfaces for data displayed in the dashboard
interface Session {
  session_id: string;
  name: string;
  storage_path: string;
  compression: string;
  encryption: string;
  created_at: string;
  updated_at: string;
}

const DashboardPage: React.FC = () => {
  const {
    sessions,
    loading,
    error,
    fetchSessions,
    createSession,
    deleteSession,
    updateSession,
  } = useSession();

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [currentSession, setCurrentSession] = useState<Partial<Session> | null>(null);
  const [isEditing, setIsEditing] = useState(false);

  const sessionColumns = [
    { key: 'name', header: 'Session Name' },
    { key: 'storage_path', header: 'Storage Path' },
    { key: 'compression', header: 'Compression' },
    { key: 'encryption', header: 'Encryption' },
    { key: 'created_at', header: 'Created At' },
  ];

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  const handleCreateSession = async () => {
    if (!currentSession || !currentSession.name || !currentSession.storage_path || !currentSession.compression || !currentSession.encryption) {
      alert('Please fill in all session details.');
      return;
    }
    await createSession(currentSession as any); // Cast to any to satisfy Omit
    setIsModalOpen(false);
    setCurrentSession(null);
  };

  const handleUpdateSession = async () => {
    if (!currentSession || !currentSession.session_id) {
      alert('Invalid session selected for update.');
      return;
    }
    await updateSession(currentSession.session_id, currentSession);
    setIsModalOpen(false);
    setCurrentSession(null);
    setIsEditing(false);
  };

  const handleDeleteSession = async (sessionId: string) => {
    if (window.confirm('Are you sure you want to delete this session?')) {
      await deleteSession(sessionId);
    }
  };

  const handleEditClick = (session: Session) => {
    setCurrentSession({ ...session });
    setIsEditing(true);
    setIsModalOpen(true);
  };

  const handleAddClick = () => {
    setCurrentSession(null);
    setIsEditing(false);
    setIsModalOpen(true);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setCurrentSession(prev => ({ ...prev, [name]: value }));
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setCurrentSession(null);
    setIsEditing(false);
  };

  return (
    <div className="container mx-auto p-4">
      <h1 className="text-2xl font-bold mb-4">Dashboard</h1>

      <div className="flex justify-end mb-4">
        <Button onClick={handleAddClick}>Add New Session</Button>
      </div>

      {loading && <p>Loading sessions...</p>}
      {error && <p className="text-red-500">Error: {error}</p>}

      {!loading && !error && (
        <Table<Session>
          data={sessions}
          columns={sessionColumns}
          onRowClick={(session) => {
            // Navigate to session details or open a modal for more info/actions
            console.log('Clicked on session:', session);
            // For now, let's just log and potentially open edit modal
            handleEditClick(session);
          }}
        />
      )}

      <Modal isOpen={isModalOpen} onClose={handleCloseModal} title={isEditing ? 'Edit Session' : 'Add New Session'}>
        <Input
          label="Session Name"
          name="name"
          value={currentSession?.name || ''}
          onChange={handleInputChange}
          error={!currentSession?.name && isModalOpen ? 'Session name is required' : ''}
        />
        <Input
          label="Storage Path"
          name="storage_path"
          value={currentSession?.storage_path || ''}
          onChange={handleInputChange}
          error={!currentSession?.storage_path && isModalOpen ? 'Storage path is required' : ''}
        />
        <Input
          label="Compression"
          name="compression"
          value={currentSession?.compression || ''}
          onChange={handleInputChange}
          error={!currentSession?.compression && isModalOpen ? 'Compression type is required' : ''}
        />
        <Input
          label="Encryption"
          name="encryption"
          value={currentSession?.encryption || ''}
          onChange={handleInputChange}
          error={!currentSession?.encryption && isModalOpen ? 'Encryption type is required' : ''}
        />
        <div className="flex justify-end mt-4">
          <Button onClick={handleCloseModal} variant="secondary" className="mr-2">
            Cancel
          </Button>
          <Button onClick={isEditing ? handleUpdateSession : handleCreateSession}>
            {isEditing ? 'Update' : 'Add'}
          </Button>
        </div>
      </Modal>

      {/* Example of how to display delete button per row if not using onRowClick for actions */}
      {/* You might want to add an 'Actions' column to the Table component */}
      {/*
      <Table<Session>
        data={sessions}
        columns={[
          ...sessionColumns,
          { key: 'actions', header: 'Actions' }
        ]}
        onRowClick={(session) => console.log('Clicked on session:', session)}
        renderCell={(row, columnKey) => {
          if (columnKey === 'actions') {
            return (
              <Button variant="danger" onClick={() => handleDeleteSession(row.session_id)}>
                Delete
              </Button>
            );
          }
          return String(row[columnKey as keyof Session]);
        }}
      />
      */}
    </div>
  );
};

export default DashboardPage;