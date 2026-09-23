import { useState } from 'react';
import {
  FolderPlus,
  FilePlus,
  FileText,
  List,
  Edit3,
  Trash2,
  Check,
  AlertCircle,
  X,
  ChevronDown,
  ChevronRight,
  Terminal,
  GitCommit,
} from 'lucide-react';
import type { ToolCall } from '../types';
import { FileDiffViewer } from './FileDiffViewer';

interface ToolBadgeProps {
  tool: ToolCall;
}

export const ToolBadge = ({ tool }: ToolBadgeProps) => {
  const [isOpen, setIsOpen] = useState(Boolean(tool.diff));

  const getToolIcon = (name: string) => {
    switch (name) {
      case 'create_folder':
        return <FolderPlus className="w-3.5 h-3.5 text-[#C9A659]" />;
      case 'create_file':
        return <FilePlus className="w-3.5 h-3.5 text-[#C9A659]" />;
      case 'read_file':
        return <FileText className="w-3.5 h-3.5 text-[#8B93A1]" />;
      case 'list_folder':
        return <List className="w-3.5 h-3.5 text-[#8B93A1]" />;
      case 'update_file':
        return <Edit3 className="w-3.5 h-3.5 text-[#C9A659]" />;
      case 'delete_item':
        return <Trash2 className="w-3.5 h-3.5 text-[#8B93A1]" />;
      default:
        return <Terminal className="w-3.5 h-3.5 text-[#8B93A1]" />;
    }
  };

  const getStatusBadge = (status: ToolCall['status']) => {
    switch (status) {
      case 'success':
        return (
          <span className="inline-flex items-center gap-1 text-[11px] text-[#C9A659] font-mono">
            <Check className="w-3 h-3 text-[#C9A659]" />
            <span>done</span>
          </span>
        );
      case 'pending_confirmation':
        return (
          <span className="inline-flex items-center gap-1 text-[11px] text-[#C9A659] font-mono">
            <AlertCircle className="w-3 h-3" />
            <span>pending</span>
          </span>
        );
      case 'cancelled':
        return (
          <span className="inline-flex items-center gap-1 text-[11px] text-[#8B93A1] font-mono">
            <X className="w-3 h-3" />
            <span>cancelled</span>
          </span>
        );
      case 'error':
        return (
          <span className="inline-flex items-center gap-1 text-[11px] text-[#e06c75] font-mono">
            <X className="w-3 h-3" />
            <span>error</span>
          </span>
        );
    }
  };

  const argSummary = Object.entries(tool.arguments)
    .map(([k, v]) => `${k}=${typeof v === 'string' ? `"${v}"` : JSON.stringify(v)}`)
    .join(', ');

  return (
    <div className="my-1.5 rounded-md border border-[#262D38] bg-[#0F1419]/80 overflow-hidden text-xs">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-3 py-2 hover:bg-[#1C232C]/60 transition-colors text-left"
      >
        <div className="flex items-center gap-2 min-w-0 pr-2">
          {getToolIcon(tool.name)}
          <span className="font-mono font-medium text-[#EDEAE3] truncate">
            {tool.name}
          </span>
          {argSummary && (
            <span className="text-[11px] text-[#8B93A1] font-mono truncate max-w-[240px]">
              ({argSummary})
            </span>
          )}
          {tool.diff && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono bg-[#161B22] border border-[#262D38] text-[#C9A659]">
              <GitCommit className="w-2.5 h-2.5" />
              diff
              {tool.diff.stats.added > 0 && <span className="text-[#98c379]">+{tool.diff.stats.added}</span>}
              {tool.diff.stats.deleted > 0 && <span className="text-[#e06c75]">-{tool.diff.stats.deleted}</span>}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {getStatusBadge(tool.status)}
          {isOpen ? (
            <ChevronDown className="w-3.5 h-3.5 text-[#8B93A1]" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5 text-[#8B93A1]" />
          )}
        </div>
      </button>

      {isOpen && (
        <div className="p-3 border-t border-[#262D38] bg-[#0F1419] space-y-2.5 text-xs font-mono">
          {tool.diff && (
            <div>
              <div className="text-[#8B93A1] text-[11px] mb-1 font-sans">
                Changes applied
              </div>
              <FileDiffViewer diff={tool.diff} />
            </div>
          )}

          <div>
            <div className="text-[#8B93A1] text-[11px] mb-1">
              arguments
            </div>
            <pre className="p-2 bg-[#161B22] rounded-md border border-[#262D38] text-[#EDEAE3] overflow-x-auto text-[11px]">
              {JSON.stringify(tool.arguments, null, 2)}
            </pre>
          </div>

          {tool.result && (
            <div>
              <div className="text-[#8B93A1] text-[11px] mb-1">
                result
              </div>
              <pre className="p-2 bg-[#161B22] rounded-md border border-[#262D38] text-[#8B93A1] overflow-x-auto whitespace-pre-wrap text-[11px]">
                {tool.result}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
