import { useState, useEffect, useRef } from 'react';
import {
  Loader2,
  Trash,
  FolderTree,
} from 'lucide-react';
import type { ChatMessage, FileNode, HealthInfo, ToolCall } from './types';
import { ToolBadge } from './components/ToolBadge';
import { ConfirmationPrompt } from './components/ConfirmationPrompt';
import { WorkspaceTree } from './components/WorkspaceTree';

const QUICK_ACTIONS = [
  "create a folder Projects",
  "make a file called notes.txt with 'hello world' inside",
  "read notes.txt",
  "update notes.txt to say 'done'",
  "delete notes.txt",
  "try reading ../../PRD.md",
];

function extractAffectedPath(toolCalls?: ToolCall[]): string | null {
  if (!toolCalls || toolCalls.length === 0) return null;
  for (const t of toolCalls) {
    const args = t.arguments || {};
    const candidate =
      args.folder_path ||
      args.file_path ||
      args.path ||
      args.target_path ||
      args.filename;
    if (candidate && typeof candidate === 'string') {
      return candidate;
    }
  }
  return null;
}

let messageCounter = 0;
const createMessageId = (prefix: string) => `${prefix}_${Date.now()}_${++messageCounter}`;

export function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [tree, setTree] = useState<FileNode | null>(null);
  const [treeLoading, setTreeLoading] = useState(false);
  const [showMobileTree, setShowMobileTree] = useState(false);
  const [highlightedPath, setHighlightedPath] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  const fetchTree = async () => {
    try {
      const res = await fetch('/api/workspace/tree');
      if (res.ok) {
        const data = await res.json();
        setTree(data);
      }
    } catch (e) {
      console.error('Failed to fetch workspace tree:', e);
    } finally {
      setTreeLoading(false);
    }
  };

  const handleResetWorkspace = async () => {
    try {
      const res = await fetch('/api/workspace/reset', { method: 'POST' });
      if (res.ok) {
        await fetchTree();
      }
    } catch (e) {
      console.error('Failed to reset workspace:', e);
    }
  };

  useEffect(() => {
    let active = true;

    const checkHealthAndTree = () => {
      fetch('/api/health')
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => {
          if (active) setHealth(data);
        })
        .catch(() => {
          if (active) setHealth(null);
        });

      fetch('/api/workspace/tree')
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => {
          if (active && data) setTree(data);
        })
        .catch(() => {});
    };

    checkHealthAndTree();
    const interval = setInterval(checkHealthAndTree, 5000);

    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  const triggerGlow = (path: string | null) => {
    if (!path) return;
    setHighlightedPath(path);
    setTimeout(() => {
      setHighlightedPath((curr) => (curr === path ? null : curr));
    }, 2400);
  };

  const handleSendMessage = async (textToSend?: string) => {
    const text = (textToSend || input).trim();
    if (!text || loading) return;

    const userMessage: ChatMessage = {
      id: createMessageId('usr'),
      role: 'user',
      content: text,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    try {
      const historyPayload = messages.map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          history: historyPayload,
        }),
      });

      const data = await response.json();

      const assistantMessage: ChatMessage = {
        id: createMessageId('ast'),
        role: 'assistant',
        content: data.reply || 'No response',
        toolCalls: data.tool_calls || [],
        confirmation: data.confirmation || undefined,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      setMessages((prev) => [...prev, assistantMessage]);

      const affected = extractAffectedPath(data.tool_calls);
      if (affected) {
        triggerGlow(affected);
      }
      await fetchTree();
    } catch (err: any) {
      const isConnectionError =
        err.message?.includes('Failed to fetch') ||
        err.message?.includes('NetworkError') ||
        err.message?.includes('Network request failed');

      const errorContent = isConnectionError
        ? '❌ **Backend Connection Failed**: Unable to reach the backend at `http://127.0.0.1:8000`.\n\nPlease ensure your FastAPI backend is running with:\n```powershell\npython -m uvicorn backend.main:app --reload --port 8000\n```'
        : `❌ Request error: ${err.message || 'Failed to connect to backend server'}`;

      const errorMessage: ChatMessage = {
        id: createMessageId('err'),
        role: 'assistant',
        content: errorContent,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const handleConfirm = async (confirmationId: string) => {
    try {
      setLoading(true);
      const res = await fetch('/api/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirmation_id: confirmationId, confirmed: true }),
      });
      const data = await res.json();
      const followUpMessage: ChatMessage = {
        id: createMessageId('ast'),
        role: 'assistant',
        content: data.reply,
        toolCalls: data.tool_calls || [],
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, followUpMessage]);

      const affected = extractAffectedPath(data.tool_calls);
      if (affected) {
        triggerGlow(affected);
      }
      await fetchTree();
    } catch (e: any) {
      console.error('Confirmation failed:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = async (confirmationId: string) => {
    try {
      setLoading(true);
      const res = await fetch('/api/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirmation_id: confirmationId, confirmed: false }),
      });
      const data = await res.json();
      const followUpMessage: ChatMessage = {
        id: createMessageId('ast'),
        role: 'assistant',
        content: data.reply,
        toolCalls: data.tool_calls || [],
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, followUpMessage]);
      await fetchTree();
    } catch (e: any) {
      console.error('Cancel failed:', e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#0F1419] text-[#EDEAE3] font-sans">
      {/* Left Panel: Live File Tree */}
      <aside
        className={`w-72 lg:w-80 shrink-0 h-full fixed inset-y-0 left-0 z-30 lg:static transition-transform duration-200 ${
          showMobileTree ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        }`}
      >
        <WorkspaceTree
          tree={tree}
          loading={treeLoading}
          highlightedPath={highlightedPath}
          onRefresh={fetchTree}
          onReset={handleResetWorkspace}
        />
      </aside>

      {/* Mobile Drawer Backdrop */}
      {showMobileTree && (
        <div
          onClick={() => setShowMobileTree(false)}
          className="fixed inset-0 bg-black/60 z-20 lg:hidden"
        />
      )}

      {/* Right Panel: Chat Interface */}
      <main className="flex flex-col flex-1 h-full min-w-0 bg-[#0F1419] shadow-[0_4px_30px_rgba(0,0,0,0.5)] z-10">
        {/* Top Header */}
        <header className="h-14 border-b border-[#262D38] px-5 flex items-center justify-between bg-[#161B22]/70 backdrop-blur shrink-0">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowMobileTree(!showMobileTree)}
              className="lg:hidden p-1.5 rounded-md text-[#8B93A1] hover:text-[#EDEAE3] hover:bg-[#1C232C]"
              title="Toggle Workspace"
            >
              <FolderTree className="w-4 h-4" />
            </button>
            <h1 className="text-sm font-semibold text-[#EDEAE3] font-sans">
              Chat with your files
            </h1>
          </div>

          <div className="flex items-center gap-3 text-xs">
            {/* Sandbox Status Indicator */}
            <div className="flex items-center gap-1.5 text-[#8B93A1] font-mono">
              <span className="w-1.5 h-1.5 rounded-full bg-[#C9A659]" />
              <span className="hidden sm:inline">sandbox:</span>
              <span className="text-[#EDEAE3]">mcp-workspace/</span>
            </div>

            {/* Model Indicator */}
            {health ? (
              <div className="hidden md:flex items-center gap-1.5 text-[11px] text-[#8B93A1] font-mono border-l border-[#262D38] pl-3">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                <span className="capitalize">{health.provider}:</span>
                <span className="text-[#EDEAE3]">{health.model}</span>
              </div>
            ) : (
              <div className="hidden md:flex items-center gap-1.5 text-[11px] text-rose-400 font-mono border-l border-[#262D38] pl-3">
                <span className="w-1.5 h-1.5 rounded-full bg-rose-500 animate-pulse" />
                <span>Backend Offline</span>
              </div>
            )}

            {/* Clear Conversation */}
            {messages.length > 0 && (
              <button
                onClick={() => setMessages([])}
                title="Clear Chat"
                className="p-1.5 text-[#8B93A1] hover:text-[#EDEAE3] hover:bg-[#1C232C] rounded-md transition-colors"
              >
                <Trash className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </header>

        {/* Conversation Stream */}
        <div className="flex-1 overflow-y-auto px-4 py-6 md:px-8 space-y-4">
          {messages.length === 0 ? (
            <div className="max-w-xl mx-auto my-auto py-16 px-4 text-center space-y-5">
              <div className="space-y-1.5">
                <h2 className="text-base font-semibold text-[#EDEAE3] font-sans">
                  Chat with your files
                </h2>
                <p className="text-xs text-[#8B93A1] max-w-md mx-auto leading-relaxed">
                  Type natural language requests below to create, read, update, or safely delete files in the sandbox.
                </p>
              </div>

              <div className="pt-2">
                <div className="flex flex-wrap justify-center gap-2 max-w-md mx-auto">
                  {QUICK_ACTIONS.map((prompt) => (
                    <button
                      key={prompt}
                      onClick={() => handleSendMessage(prompt)}
                      className="text-xs font-mono bg-[#161B22] hover:bg-[#1C232C] border border-[#262D38] hover:border-[#C9A659]/50 text-[#8B93A1] hover:text-[#EDEAE3] px-3 py-1.5 rounded-md transition-colors text-left"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto space-y-4">
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex ${
                    msg.role === 'user' ? 'justify-end' : 'justify-start'
                  }`}
                >
                  <div
                    className={`max-w-[90%] md:max-w-[85%] rounded-md p-3.5 border ${
                      msg.role === 'user'
                        ? 'bg-[#161B22] border-[#262D38] text-[#EDEAE3]'
                        : 'bg-[#161B22]/60 border-[#262D38]/80 text-[#EDEAE3]'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3 mb-1.5 pb-1 border-b border-[#262D38]/40 text-[11px] text-[#8B93A1] font-mono">
                      <span className="font-sans font-medium text-[#EDEAE3]">
                        {msg.role === 'user' ? 'You' : 'Assistant'}
                      </span>
                      <span>{msg.timestamp}</span>
                    </div>

                    <div className="text-xs md:text-sm leading-relaxed whitespace-pre-wrap">
                      {msg.content}
                    </div>

                    {/* Render MCP Tool Badges */}
                    {msg.toolCalls && msg.toolCalls.length > 0 && (
                      <div className="mt-2.5 pt-2 border-t border-[#262D38]/60 space-y-1">
                        {msg.toolCalls.map((tool, idx) => (
                          <ToolBadge key={idx} tool={tool} />
                        ))}
                      </div>
                    )}

                    {/* Render Interactive Confirmation Card */}
                    {msg.confirmation && (
                      <ConfirmationPrompt
                        confirmation={msg.confirmation}
                        onConfirm={handleConfirm}
                        onCancel={handleCancel}
                      />
                    )}
                  </div>
                </div>
              ))}

              {loading && (
                <div className="flex items-center gap-2 text-[#8B93A1] text-xs font-mono py-2">
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-[#C9A659]" />
                  <span>Executing command...</span>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Calm Command-Line Input Bar */}
        <div className="border-t border-[#262D38] p-4 bg-[#161B22] shrink-0">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSendMessage();
            }}
            className="max-w-3xl mx-auto flex items-center gap-2.5 bg-[#0F1419] border border-[#262D38] rounded-md px-3.5 py-2.5 focus-within:border-[#C9A659] transition-colors"
          >
            <span className="text-[#C9A659] font-mono text-sm font-semibold select-none">
              &gt;
            </span>

            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="type a command..."
              disabled={loading}
              className="flex-1 bg-transparent border-0 focus:outline-none text-[#EDEAE3] font-mono text-xs md:text-sm placeholder-[#8B93A1]"
            />

            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="px-2 py-1 text-[#8B93A1] hover:text-[#C9A659] disabled:opacity-30 disabled:hover:text-[#8B93A1] transition-colors font-mono text-xs flex items-center gap-1"
              title="Send command"
            >
              <span>➤</span>
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}

export default App;
