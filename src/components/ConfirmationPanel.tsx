import React from 'react';
import { Check, X, AlertTriangle } from 'lucide-react';
import axios from 'axios';
import { handleError } from './Toast';

interface PendingAction {
  id: string;
  project_id: string;
  action_type: string;
  original_user_message: string;
  proposed_changes: any;
}

interface ConfirmationPanelProps {
  action: PendingAction;
  onConfirm: () => void;
  onCancel: () => void;
}

export const ConfirmationPanel: React.FC<ConfirmationPanelProps> = ({ action, onConfirm, onCancel }) => {
  const handleConfirm = async () => {
    try {
      await axios.post(`/api/confirm-action/${action.id}?project_id=${action.project_id}`);
      onConfirm();
    } catch (error) {
      handleError("Failed to confirm the action.", error);
    }
  };

  const handleCancel = async () => {
    try {
      await axios.post(`/api/cancel-action/${action.id}?project_id=${action.project_id}`);
      onCancel();
    } catch (error) {
      handleError("Failed to cancel the action.", error);
    }
  };

  return (
    <div className="bg-white border border-amber-200 rounded-lg p-4 shadow-sm my-4">
      <div className="flex items-start gap-3">
        <AlertTriangle className="text-amber-500 mt-0.5" size={20} />
        <div className="flex-1">
          <h3 className="font-semibold text-amber-900">Pending {action.action_type}</h3>
          <p className="text-sm text-amber-700 mt-1">
            You have a pending change based on: "{action.original_user_message}"
          </p>
          <div className="mt-4 flex gap-2">
            <button
              onClick={handleConfirm}
              className="flex items-center gap-1 bg-amber-600 hover:bg-amber-700 text-white px-3 py-1.5 rounded text-sm font-medium"
            >
              <Check size={16} /> Confirm
            </button>
            <button
              onClick={handleCancel}
              className="flex items-center gap-1 bg-gray-100 hover:bg-gray-200 text-gray-700 px-3 py-1.5 rounded text-sm font-medium"
            >
              <X size={16} /> Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
