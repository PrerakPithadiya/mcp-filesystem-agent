import { useState } from 'react';
import { AlertTriangle, Trash2, X, Loader2 } from 'lucide-react';
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
    <div className="my-3 p-4 rounded-xl border border-amber-500/40 bg-amber-950/20 backdrop-blur-sm shadow-lg">
      <div className="flex items-start gap-3">
        <div className="p-2 rounded-lg bg-amber-500/20 text-amber-400 mt-0.5">
          <AlertTriangle className="w-5 h-5" />
        </div>
        <div className="flex-1">
          <h4 className="text-sm font-semibold text-amber-200">
            Safety Confirmation Required
          </h4>
          <p className="text-xs text-amber-300/80 mt-1">
            The chatbot is requesting to permanently delete{' '}
            <strong className="text-white underline font-mono">
              {confirmation.target}
            </strong>
            . This cannot be undone.
          </p>

          <div className="flex items-center gap-2 mt-3.5">
            <button
              onClick={() => handleAction(true)}
              disabled={loading}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-rose-600 hover:bg-rose-500 disabled:opacity-50 text-white text-xs font-medium rounded-lg shadow transition-colors"
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
              className="flex items-center gap-1 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-slate-300 text-xs font-medium rounded-lg transition-colors"
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
