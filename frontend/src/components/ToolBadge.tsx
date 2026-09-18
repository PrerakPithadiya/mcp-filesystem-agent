import { useState } from 'react';
import {
  FolderPlus,
  FilePlus,
  FileText,
  List,
  Edit3,
  Trash2,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ChevronDown,
  ChevronRight,
  Terminal,
} from 'lucide-react';
import type { ToolCall } from '../types';

interface ToolBadgeProps {
  tool: ToolCall;
}

export const ToolBadge = ({ tool }: ToolBadgeProps) => {
  const [isOpen, setIsOpen] = useState(false);

  const getToolIcon = (name: string) => {
    switch (name) {
      case 'create_folder':
        return <FolderPlus className="w-4 h-4 text-emerald-400" />;
      case 'create_file':
        return <FilePlus className="w-4 h-4 text-blue-400" />;
      case 'read_file':
        return <FileText className="w-4 h-4 text-indigo-400" />;
      case 'list_folder':
        return <List className="w-4 h-4 text-cyan-400" />;
      case 'update_file':
        return <Edit3 className="w-4 h-4 text-amber-400" />;
      case 'delete_item':
        return <Trash2 className="w-4 h-4 text-rose-400" />;
      default:
        return <Terminal className="w-4 h-4 text-purple-400" />;
    }
  };

  const getStatusBadge = (status: ToolCall['status']) => {
    switch (status) {
      case 'success':
        return (
          <span className="flex items-center gap-1 text-xs text-emerald-400 font-medium bg-emerald-950/60 border border-emerald-800/60 px-2 py-0.5 rounded-full">
            <CheckCircle2 className="w-3 h-3" /> Executed
          </span>
        );
      case 'pending_confirmation':
        return (
          <span className="flex items-center gap-1 text-xs text-amber-400 font-medium bg-amber-950/60 border border-amber-800/60 px-2 py-0.5 rounded-full animate-pulse">
            <AlertTriangle className="w-3 h-3" /> Needs Confirmation
          </span>
        );
      case 'cancelled':
        return (
          <span className="flex items-center gap-1 text-xs text-zinc-400 font-medium bg-zinc-800/60 border border-zinc-700/60 px-2 py-0.5 rounded-full">
            <XCircle className="w-3 h-3" /> Cancelled
          </span>
        );
      case 'error':
        return (
          <span className="flex items-center gap-1 text-xs text-rose-400 font-medium bg-rose-950/60 border border-rose-800/60 px-2 py-0.5 rounded-full">
            <XCircle className="w-3 h-3" /> Error
          </span>
        );
    }
  };

  return (
    <div className="my-2 rounded-lg border border-slate-800 bg-slate-900/80 overflow-hidden text-sm">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between p-2.5 hover:bg-slate-800/50 transition-colors text-left"
      >
        <div className="flex items-center gap-2">
          {getToolIcon(tool.name)}
          <span className="font-mono font-medium text-slate-200">
            {tool.name}
          </span>
          <span className="text-xs text-slate-500 font-mono">
            ({Object.keys(tool.arguments).join(', ')})
          </span>
        </div>
        <div className="flex items-center gap-2">
          {getStatusBadge(tool.status)}
          {isOpen ? (
            <ChevronDown className="w-4 h-4 text-slate-400" />
          ) : (
            <ChevronRight className="w-4 h-4 text-slate-400" />
          )}
        </div>
      </button>

      {isOpen && (
        <div className="p-3 border-t border-slate-800 bg-slate-950/70 space-y-2 text-xs font-mono">
          <div>
            <div className="text-slate-400 font-semibold mb-1 uppercase tracking-wider text-[10px]">
              Parameters:
            </div>
            <pre className="p-2 bg-slate-900 rounded border border-slate-800 text-cyan-300 overflow-x-auto">
              {JSON.stringify(tool.arguments, null, 2)}
            </pre>
          </div>

          {tool.result && (
            <div>
              <div className="text-slate-400 font-semibold mb-1 uppercase tracking-wider text-[10px]">
                MCP Server Output:
              </div>
              <pre className="p-2 bg-slate-900 rounded border border-slate-800 text-slate-300 overflow-x-auto whitespace-pre-wrap">
                {tool.result}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
