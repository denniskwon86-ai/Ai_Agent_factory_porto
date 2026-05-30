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