import { useState, useEffect } from 'react';
import { FileText, Copy, Check, X, WrapText } from 'lucide-react';

interface CodePreviewModalProps {
  isOpen: boolean;
  filePath: string | null;
  content: string | null;
  onClose: () => void;
}

export const CodePreviewModal = ({
  isOpen,
  filePath,
  content,
  onClose,
}: CodePreviewModalProps) => {
  const [copied, setCopied] = useState(false);
  const [wordWrap, setWordWrap] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    if (isOpen) {
      window.addEventListener('keydown', handleKeyDown);
    }
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen || !filePath) return null;

  const lines = (content ?? '').split('\n');

  const handleCopy = () => {
    if (content !== null) {
      navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4 animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div
        className="w-full max-w-4xl max-h-[85vh] flex flex-col bg-[#161B22] border border-[#262D38] rounded-xl shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="min-h-14 px-5 border-b border-[#262D38] flex flex-wrap items-center gap-3 shrink-0 bg-[#0F1419] py-3">
          <div className="flex items-center gap-2.5 min-w-0 flex-1">
            <FileText className="w-4 h-4 text-[#C9A659] shrink-0" />
            <span className="font-mono text-xs font-medium text-[#EDEAE3] truncate">
              {filePath}
            </span>
            <span className="text-[11px] font-mono text-[#8B93A1] bg-[#161B22] px-2 py-0.5 rounded border border-[#262D38] shrink-0 ml-2">
              {lines.length} {lines.length === 1 ? 'line' : 'lines'}
            </span>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={() => setWordWrap(!wordWrap)}
              title={wordWrap ? 'Disable Word Wrap' : 'Enable Word Wrap'}
              className={`p-1.5 rounded-md text-xs font-mono flex items-center gap-1 border transition-colors ${
                wordWrap
                  ? 'bg-[#C9A659]/15 border-[#C9A659]/40 text-[#C9A659]'
                  : 'bg-[#161B22] border-[#262D38] text-[#8B93A1] hover:text-[#EDEAE3]'
              }`}
            >
              <WrapText className="w-3.5 h-3.5" />
              <span className="text-[11px] hidden sm:inline">Wrap</span>
            </button>

            <button
              onClick={handleCopy}
              className="p-1.5 px-2.5 rounded-md text-xs font-mono flex items-center gap-1.5 bg-[#161B22] border border-[#262D38] text-[#8B93A1] hover:text-[#EDEAE3] transition-colors"
            >
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5 text-[#98c379]" />
                  <span className="text-[#98c379] text-[11px]">Copied</span>
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" />
                  <span className="text-[11px]">Copy</span>
                </>
              )}
            </button>

            <button
              onClick={onClose}
              title="Close (Esc)"
              className="p-1.5 text-[#8B93A1] hover:text-[#EDEAE3] hover:bg-[#262D38]/50 rounded-md transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Modal Code Viewer */}
        <div className="flex-1 overflow-auto bg-[#0F1419] p-4 text-xs font-mono">
          {content === '' ? (
            <div className="text-center py-12 text-[#8B93A1] italic">Empty file</div>
          ) : (
            <div className="table w-full border-collapse">
              {lines.map((line, idx) => (
                <div key={idx} className="table-row hover:bg-[#161B22]/50">
                  <div className="table-cell select-none text-right pr-4 text-[#8B93A1]/40 w-12 border-r border-[#262D38]/40 align-top">
                    {idx + 1}
                  </div>
                  <div
                    className={`table-cell pl-4 text-[#EDEAE3] ${
                      wordWrap ? 'whitespace-pre-wrap break-all' : 'whitespace-pre overflow-x-auto'
                    }`}
                  >
                    {line || ' '}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
