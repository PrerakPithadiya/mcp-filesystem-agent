import { useState } from 'react';
import {
  Folder,
  FolderOpen,
  FileText,
  RefreshCw,
  RotateCcw,
  Eye,
  X,
  HardDrive,
  Loader2,
} from 'lucide-react';
import type { FileNode } from '../types';

interface WorkspaceTreeProps {
  tree: FileNode | null;
  loading: boolean;
  onRefresh: () => void;
  onReset: () => void;
}

export const WorkspaceTree = ({
  tree,
  loading,
  onRefresh,
  onReset,
}: WorkspaceTreeProps) => {
  const [selectedFile, setSelectedFile] = useState<{
    path: string;
    content: string;
  } | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  const handleFileClick = async (path: string) => {
    try {
      setPreviewLoading(true);
      const res = await fetch(`/api/workspace/file?path=${encodeURIComponent(path)}`);
      if (res.ok) {
        const data = await res.json();
        setSelectedFile({ path, content: data.content });
      }
    } catch (e) {
      console.error('Failed to preview file:', e);
    } finally {
      setPreviewLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-slate-900/90 border-l border-slate-800">
      {/* Header */}
      <div className="p-4 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <HardDrive className="w-5 h-5 text-indigo-400" />
          <div>
            <h3 className="text-sm font-semibold text-white flex items-center gap-1.5">
              Live Workspace
              <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            </h3>
            <p className="text-[11px] text-slate-400 font-mono">
              mcp-workspace/
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <button
            onClick={onRefresh}
            disabled={loading}
            title="Refresh Files"
            className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-md transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={onReset}
            disabled={loading}
            title="Reset Workspace"
            className="p-1.5 text-slate-400 hover:text-rose-400 hover:bg-slate-800 rounded-md transition-colors"
          >
            <RotateCcw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Tree Content */}
      <div className="flex-1 overflow-y-auto p-3">
        {!tree || (!tree.children || tree.children.length === 0) ? (
          <div className="text-center py-12 px-4 text-slate-500 text-xs">
            <Folder className="w-8 h-8 mx-auto mb-2 opacity-40" />
            <p>Workspace is currently empty.</p>
            <p className="mt-1 text-[11px] text-slate-600">
              Ask Gemini to create folders or files!
            </p>
          </div>
        ) : (
          <div className="space-y-0.5">
            {tree.children.map((child) => (
              <TreeNode
                key={child.path || child.name}
                node={child}
                onSelectFile={handleFileClick}
              />
            ))}
          </div>
        )}
      </div>

      {/* File Preview Drawer */}
      {selectedFile && (
        <div className="border-t border-slate-800 bg-slate-950 p-3 max-h-60 flex flex-col">
          <div className="flex items-center justify-between pb-2 border-b border-slate-800 text-xs">
            <span className="font-mono text-cyan-400 truncate flex items-center gap-1.5">
              {previewLoading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-400" />
              ) : (
                <Eye className="w-3.5 h-3.5" />
              )}
              {selectedFile.path}
            </span>
            <button
              onClick={() => setSelectedFile(null)}
              className="text-slate-400 hover:text-white"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          <pre className="mt-2 text-xs font-mono text-slate-300 overflow-auto whitespace-pre-wrap flex-1 bg-slate-900/60 p-2 rounded">
            {selectedFile.content || <span className="text-slate-600 italic">Empty file</span>}
          </pre>
        </div>
      )}
    </div>
  );
};

interface TreeNodeProps {
  node: FileNode;
  onSelectFile: (path: string) => void;
  level?: number;
}

const TreeNode = ({ node, onSelectFile, level = 0 }: TreeNodeProps) => {
  const [open, setOpen] = useState(true);

  if (node.type === 'directory') {
    return (
      <div>
        <button
          onClick={() => setOpen(!open)}
          className="w-full flex items-center gap-2 py-1 px-2 hover:bg-slate-800/60 rounded text-left text-xs text-slate-300 hover:text-white transition-colors"
          style={{ paddingLeft: `${level * 14 + 8}px` }}
        >
          {open ? (
            <FolderOpen className="w-4 h-4 text-amber-400 shrink-0" />
          ) : (
            <Folder className="w-4 h-4 text-amber-400 shrink-0" />
          )}
          <span className="font-medium truncate">{node.name}</span>
          <span className="text-[10px] text-slate-500 font-mono">
            ({node.children?.length || 0})
          </span>
        </button>

        {open && node.children && (
          <div>
            {node.children.map((child) => (
              <TreeNode
                key={child.path || child.name}
                node={child}
                onSelectFile={onSelectFile}
                level={level + 1}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <button
      onClick={() => onSelectFile(node.path)}
      className="w-full flex items-center justify-between py-1 px-2 hover:bg-slate-800/60 rounded text-left text-xs text-slate-400 hover:text-cyan-300 transition-colors group"
      style={{ paddingLeft: `${level * 14 + 8}px` }}
    >
      <div className="flex items-center gap-2 truncate">
        <FileText className="w-3.5 h-3.5 text-blue-400 shrink-0" />
        <span className="truncate font-mono">{node.name}</span>
      </div>
      <span className="text-[10px] text-slate-600 font-mono shrink-0 group-hover:text-slate-400">
        {node.size !== undefined ? `${node.size} B` : ''}
      </span>
    </button>
  );
};
