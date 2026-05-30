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