import { useState } from 'react';
import { AlertCircle, Trash2, X, Loader2 } from 'lucide-react';
import type { ConfirmationInfo } from '../types';

interface ConfirmationPromptProps {
  confirmation: ConfirmationInfo;
  onConfirm: (confirmationId: string) => Promise<void>;
  onCancel: (confirmationId: string) => Promise<void>;
}

export const ConfirmationPrompt = ({
  confirmation,
  onConfirm,
  onCancel,
}: ConfirmationPromptProps) => {
  const [loading, setLoading] = useState(false);
  const [responded, setResponded] = useState(false);

  const handleAction = async (confirmed: boolean) => {
    setLoading(true);
    try {
      if (confirmed) {
        await onConfirm(confirmation.id);
      } else {
        await onCancel(confirmation.id);
      }
      setResponded(true);
    } finally {
      setLoading(false);
    }
  };

  if (responded) {
    return null;
  }

  return (
    <div className="my-2.5 p-3.5 rounded-md border border-[#262D38] bg-[#161B22] text-xs">
      <div className="flex items-start gap-2.5">
        <div className="p-1 text-[#C9A659] mt-0.5">
          <AlertCircle className="w-4 h-4" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-medium text-[#EDEAE3] font-sans">
            Confirm permanent deletion
          </div>
          <p className="text-[#8B93A1] mt-1 leading-relaxed">
            The agent is requesting to delete{' '}
            <span className="font-mono text-[#EDEAE3] bg-[#0F1419] px-1.5 py-0.5 rounded border border-[#262D38]">
              {confirmation.target}
            </span>
            . This action cannot be undone.
          </p>

          <div className="flex items-center gap-2 mt-3">
            <button
              onClick={() => handleAction(true)}
              disabled={loading}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-[#2A1D20] border border-[#522931] hover:bg-[#382329] text-[#f87171] disabled:opacity-50 text-xs font-medium rounded-md transition-colors"
            >
              {loading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Trash2 className="w-3.5 h-3.5" />
              )}
              Confirm Delete
            </button>

            <button
              onClick={() => handleAction(false)}
              disabled={loading}
              className="flex items-center gap-1 px-3 py-1.5 bg-[#0F1419] border border-[#262D38] hover:bg-[#1C232C] disabled:opacity-50 text-[#8B93A1] hover:text-[#EDEAE3] text-xs font-medium rounded-md transition-colors"
            >
              <X className="w-3.5 h-3.5" />
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
