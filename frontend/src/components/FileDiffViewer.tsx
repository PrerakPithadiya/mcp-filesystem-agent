import { GitCommit, Plus, Minus } from 'lucide-react';
import type { FileDiffData } from '../types';

interface FileDiffViewerProps {
  diff: FileDiffData;
}

export const FileDiffViewer = ({ diff }: FileDiffViewerProps) => {
  const { file_path, stats, lines } = diff;

  return (
    <div className="rounded-md border border-[#262D38] bg-[#0F1419] overflow-hidden my-2 text-xs font-mono">
      {/* Header bar */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-[#161B22] border-b border-[#262D38]">
        <div className="flex items-center gap-1.5 truncate">
          <GitCommit className="w-3.5 h-3.5 text-[#C9A659]" />
          <span className="text-[#EDEAE3] font-medium truncate">{file_path}</span>
        </div>
        <div className="flex items-center gap-2 shrink-0 text-[11px]">
          {stats.added > 0 && (
            <span className="flex items-center text-[#98c379] bg-[#98c379]/10 px-1.5 py-0.5 rounded">
              <Plus className="w-3 h-3 mr-0.5" />
              {stats.added}
            </span>
          )}
          {stats.deleted > 0 && (
            <span className="flex items-center text-[#e06c75] bg-[#e06c75]/10 px-1.5 py-0.5 rounded">
              <Minus className="w-3 h-3 mr-0.5" />
              {stats.deleted}
            </span>
          )}
          {stats.added === 0 && stats.deleted === 0 && (
            <span className="text-[#8B93A1]">no changes</span>
          )}
        </div>
      </div>

      {/* Diff line container */}
      <div className="overflow-x-auto max-h-72 divide-y divide-[#262D38]/30">
        {lines.length === 0 ? (
          <div className="p-3 text-[#8B93A1] italic">Empty file or no line changes.</div>
        ) : (
          lines.map((l, index) => {
            const isAdd = l.type === 'add';
            const isDelete = l.type === 'delete';

            let rowBg = 'hover:bg-[#161B22]/50 text-[#8B93A1]';
            let prefix = ' ';
            let prefixColor = 'text-[#8B93A1]';

            if (isAdd) {
              rowBg = 'bg-[#98c379]/10 text-[#EDEAE3] hover:bg-[#98c379]/15';
              prefix = '+';
              prefixColor = 'text-[#98c379] font-bold';
            } else if (isDelete) {
              rowBg = 'bg-[#e06c75]/10 text-[#EDEAE3]/80 hover:bg-[#e06c75]/15 line-through decoration-[#e06c75]/50';
              prefix = '-';
              prefixColor = 'text-[#e06c75] font-bold';
            }

            return (
              <div
                key={index}
                className={`flex items-stretch text-[11px] leading-5 font-mono select-text ${rowBg}`}
              >
                {/* Old line number */}
                <div className="w-8 shrink-0 text-right pr-2 text-[#8B93A1]/50 border-r border-[#262D38]/40 select-none">
                  {l.old_num ?? ''}
                </div>
                {/* New line number */}
                <div className="w-8 shrink-0 text-right pr-2 text-[#8B93A1]/50 border-r border-[#262D38]/40 select-none">
                  {l.new_num ?? ''}
                </div>
                {/* Prefix symbol */}
                <div className={`w-5 shrink-0 text-center select-none ${prefixColor}`}>
                  {prefix}
                </div>
                {/* Line text */}
                <div className="flex-1 px-1 whitespace-pre overflow-x-auto">
                  {l.content || ' '}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
