import { useState } from 'react';
import {
  Folder,
  FolderOpen,
  FileText,
  RefreshCw,
  RotateCcw,
  Eye,
  X,
  FolderTree,
  Loader2,
  Check,
} from 'lucide-react';
import type { FileNode } from '../types';

interface WorkspaceTreeProps {
  tree: FileNode | null;
  loading: boolean;
  highlightedPath?: string | null;
  onRefresh: () => void;
  onReset: () => void;
}

const normalize = (p: string) => p.replace(/^\.?\/+/, '').replace(/\/+$/, '').toLowerCase();

const isPathMatch = (nodePath: string, nodeName: string, highlight?: string | null) => {
  if (!highlight) return false;
  const nHighlight = normalize(highlight);
  const nPath = normalize(nodePath);
  const nName = normalize(nodeName);
  return (
    nPath === nHighlight ||
    nName === nHighlight ||
    nHighlight.endsWith('/' + nPath) ||
    nHighlight.endsWith('/' + nName)
  );
};

export const WorkspaceTree = ({
  tree,
  loading,
  highlightedPath,
  onRefresh,
  onReset,
}: WorkspaceTreeProps) => {
  const [selectedFile, setSelectedFile] = useState<{
    path: string;
    content: string;
  } | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [showResetConfirm, setShowResetConfirm] = useState(false);

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

  const handleConfirmReset = () => {
    setShowResetConfirm(false);
    onReset();
  };

  const isEmpty = !tree || !tree.children || tree.children.length === 0;

  return (
    <div className="flex flex-col h-full bg-[#161B22] border-r border-[#262D38] select-none">
      {/* Header */}
      <div className="h-14 px-4 border-b border-[#262D38] flex items-center justify-between shrink-0 bg-[#161B22]">
        <div className="flex items-center gap-2">
          <FolderTree className="w-4 h-4 text-[#C9A659]" />
          <span className="text-xs font-semibold text-[#EDEAE3] font-sans tracking-wide">
            WORKSPACE
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          {showResetConfirm ? (
            <div className="flex items-center gap-1 text-[11px] bg-[#0F1419] border border-[#262D38] px-1.5 py-0.5 rounded-md">
              <span className="text-[#8B93A1]">Reset?</span>
              <button
                onClick={handleConfirmReset}
                title="Confirm reset"
                className="text-[#C9A659] hover:text-white p-0.5"
              >
                <Check className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => setShowResetConfirm(false)}
                title="Cancel"
                className="text-[#8B93A1] hover:text-white p-0.5"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          ) : (
            <>
              <button
                onClick={onRefresh}
                disabled={loading}
                title="Refresh Workspace"
                className="p-1.5 text-[#8B93A1] hover:text-[#EDEAE3] hover:bg-[#1C232C] rounded-md transition-colors"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              </button>
              <button
                onClick={() => setShowResetConfirm(true)}
                disabled={loading}
                title="Reset Workspace"
                className="p-1.5 text-[#8B93A1] hover:text-[#C9A659] hover:bg-[#1C232C] rounded-md transition-colors"
              >
                <RotateCcw className="w-3.5 h-3.5" />
              </button>
            </>
          )}
        </div>
      </div>

      {/* Tree Content */}
      <div className="flex-1 overflow-y-auto p-2.5">
        {isEmpty ? (
          <div className="py-10 px-4 text-center">
            <p className="text-xs text-[#8B93A1] leading-relaxed">
              This folder is empty — try 'create a file called notes.txt'
            </p>
          </div>
        ) : (
          <div className="space-y-0.5">
            {/* Root workspace item */}
            <div className="flex items-center gap-1.5 px-2 py-1 text-xs text-[#8B93A1] font-mono">
              <FolderOpen className="w-3.5 h-3.5 text-[#C9A659]" />
              <span className="truncate">mcp-workspace</span>
            </div>

            <div className="pl-3 border-l border-[#262D38]/40 ml-2 space-y-0.5">
              {tree?.children?.map((child) => (
                <TreeNode
                  key={child.path || child.name}
                  node={child}
                  highlightedPath={highlightedPath}
                  onSelectFile={handleFileClick}
                />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* File Preview Drawer */}
      {selectedFile && (
        <div className="border-t border-[#262D38] bg-[#0F1419] p-3 max-h-64 flex flex-col shrink-0">
          <div className="flex items-center justify-between pb-2 border-b border-[#262D38] text-xs">
            <span className="font-mono text-[#EDEAE3] truncate flex items-center gap-1.5">
              {previewLoading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin text-[#C9A659]" />
              ) : (
                <Eye className="w-3.5 h-3.5 text-[#8B93A1]" />
              )}
              {selectedFile.path}
            </span>
            <button
              onClick={() => setSelectedFile(null)}
              className="text-[#8B93A1] hover:text-[#EDEAE3] p-0.5"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          <pre className="mt-2 text-xs font-mono text-[#EDEAE3] overflow-auto whitespace-pre-wrap flex-1 bg-[#161B22] p-2.5 rounded-md border border-[#262D38]">
            {selectedFile.content || <span className="text-[#8B93A1] italic">Empty file</span>}
          </pre>
        </div>
      )}
    </div>
  );
};

interface TreeNodeProps {
  node: FileNode;
  highlightedPath?: string | null;
  onSelectFile: (path: string) => void;
  level?: number;
}

const TreeNode = ({ node, highlightedPath, onSelectFile, level = 0 }: TreeNodeProps) => {
  const [open, setOpen] = useState(true);
  const isHighlighted = isPathMatch(node.path, node.name, highlightedPath);

  if (node.type === 'directory') {
    return (
      <div>
        <button
          onClick={() => setOpen(!open)}
          className={`w-full flex items-center gap-2 py-1 px-2 rounded-md text-left text-xs transition-colors duration-150 ${
            isHighlighted
              ? 'animate-brass-glow text-[#EDEAE3]'
              : 'text-[#EDEAE3] hover:bg-[#1C232C]'
          }`}
          style={{ paddingLeft: `${level * 12 + 6}px` }}
        >
          {open ? (
            <FolderOpen className="w-3.5 h-3.5 text-[#C9A659] shrink-0" />
          ) : (
            <Folder className="w-3.5 h-3.5 text-[#C9A659] shrink-0" />
          )}
          <span className="font-sans font-medium truncate">{node.name}</span>
          <span className="text-[10px] text-[#8B93A1] font-mono ml-auto">
            {node.children?.length || 0}
          </span>
        </button>

        {open && node.children && (
          <div className="space-y-0.5">
            {node.children.map((child) => (
              <TreeNode
                key={child.path || child.name}
                node={child}
                highlightedPath={highlightedPath}
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
      className={`w-full flex items-center justify-between py-1 px-2 rounded-md text-left text-xs transition-colors duration-150 group ${
        isHighlighted
          ? 'animate-brass-glow text-[#EDEAE3]'
          : 'text-[#EDEAE3] hover:bg-[#1C232C]'
      }`}
      style={{ paddingLeft: `${level * 12 + 6}px` }}
    >
      <div className="flex items-center gap-2 truncate">
        <FileText className="w-3.5 h-3.5 text-[#8B93A1] group-hover:text-[#EDEAE3] shrink-0" />
        <span className="truncate font-mono text-[12px]">{node.name}</span>
      </div>
      {node.size !== undefined && (
        <span className="text-[10px] text-[#8B93A1] font-mono shrink-0 ml-2">
          {node.size} B
        </span>
      )}
    </button>
  );
};
