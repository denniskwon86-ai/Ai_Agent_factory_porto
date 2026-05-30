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