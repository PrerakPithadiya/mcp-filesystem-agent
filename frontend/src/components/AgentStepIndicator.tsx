import { Sparkles, Cog, PenLine } from 'lucide-react';

interface AgentStepIndicatorProps {
  stage?: 'thinking' | 'calling_tools' | 'generating' | 'done';
  message?: string;
  activeToolName?: string | null;
}

export const AgentStepIndicator = ({
  stage = 'thinking',
  message,
  activeToolName,
}: AgentStepIndicatorProps) => {
  if (stage === 'done') return null;

  return (
    <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#161B22] border border-[#262D38] text-xs text-[#EDEAE3] my-2 select-none shadow-sm animate-pulse">
      {stage === 'thinking' && (
        <>
          <Sparkles className="w-3.5 h-3.5 text-[#C9A659] animate-spin" />
          <span className="font-sans text-[11px] text-[#C9A659] font-medium">
            {message || 'Analyzing intent & resolving tools...'}
          </span>
        </>
      )}

      {stage === 'calling_tools' && (
        <>
          <Cog className="w-3.5 h-3.5 text-[#C9A659] animate-spin" />
          <span className="font-mono text-[11px] text-[#EDEAE3]">
            {activeToolName ? (
              <>
                Running tool <span className="text-[#C9A659]">{activeToolName}()</span>...
              </>
            ) : (
              message || 'Executing filesystem actions...'
            )}
          </span>
        </>
      )}

      {stage === 'generating' && (
        <>
          <PenLine className="w-3.5 h-3.5 text-[#C9A659] animate-pulse" />
          <span className="font-sans text-[11px] text-[#8B93A1]">
            {message || 'Streaming response...'}
          </span>
        </>
      )}
    </div>
  );
};
