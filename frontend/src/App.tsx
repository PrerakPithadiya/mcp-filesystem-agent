import { useState, useEffect, useRef } from 'react';
import {
  Send,
  Bot,
  User,
  ShieldCheck,
  Cpu,
  Sparkles,
  Loader2,
  Trash,
  FolderTree,
} from 'lucide-react';
import type { ChatMessage, FileNode, HealthInfo } from './types';
import { ToolBadge } from './components/ToolBadge';
import { ConfirmationPrompt } from './components/ConfirmationPrompt';
import { WorkspaceTree } from './components/WorkspaceTree';

const QUICK_ACTIONS = [
  "Create a folder called Projects",
  "Make a file called notes.txt with 'hello world' inside",
  "Read the file notes.txt",
  "Update notes.txt to say 'done'",
  "Delete the file notes.txt",
  "Try reading ../../PRD.md",
];

export function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [tree, setTree] = useState<FileNode | null>(null);
  const [treeLoading, setTreeLoading] = useState(false);
  const [showMobileTree, setShowMobileTree] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  const fetchHealth = async () => {
    try {
      const res = await fetch('/api/health');
      if (res.ok) {
        const data = await res.json();
        setHealth(data);
      }
    } catch (e) {
      console.error('Health check failed:', e);
    }
  };

  const fetchTree = async () => {
    try {
      setTreeLoading(true);
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
    if (!window.confirm('Reset workspace to default starter file?')) return;
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
    fetchHealth();
    fetchTree();
  }, []);

  const handleSendMessage = async (textToSend?: string) => {
    const text = (textToSend || input).trim();
    if (!text || loading) return;

    const userMessage: ChatMessage = {
      id: `usr_${Date.now()}`,
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
        id: `ast_${Date.now()}`,
        role: 'assistant',
        content: data.reply || 'No response',
        toolCalls: data.tool_calls || [],
        confirmation: data.confirmation || undefined,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      setMessages((prev) => [...prev, assistantMessage]);
      await fetchTree();
    } catch (err: any) {
      const errorMessage: ChatMessage = {
        id: `err_${Date.now()}`,
        role: 'assistant',
        content: `❌ Request error: ${err.message || 'Failed to connect to backend server'}`,
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
        id: `ast_${Date.now()}`,
        role: 'assistant',
        content: data.reply,
        toolCalls: data.tool_calls || [],
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, followUpMessage]);
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
        id: `ast_${Date.now()}`,
        role: 'assistant',
        content: data.reply,
        toolCalls: data.tool_calls || [],
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, followUpMessage]);
    } catch (e: any) {
      console.error('Cancel failed:', e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-950 text-slate-100">
      {/* Main Chat Pane */}
      <div className="flex flex-col flex-1 h-full min-w-0">
        {/* Top Header */}
        <header className="h-16 border-b border-slate-800 px-6 flex items-center justify-between bg-slate-900/60 backdrop-blur shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-600 to-cyan-500 flex items-center justify-center shadow-lg shadow-indigo-500/20">
              <Cpu className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-base font-bold tracking-tight text-white flex items-center gap-2">
                MCP Filesystem Chatbot
                <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                  FastMCP Protocol
                </span>
              </h1>
              <p className="text-xs text-slate-400">
                Natural Language File Operations Powered by Google Gemini
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Status pill */}
            <div className="hidden sm:flex items-center gap-2 text-xs bg-slate-800/80 border border-slate-700/60 px-3 py-1.5 rounded-full">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
              <span className="text-slate-300">Sandbox:</span>
              <span className="font-mono text-emerald-400 text-[11px]">mcp-workspace/</span>
            </div>

            {/* LLM indicator */}
            {health && (
              <div className="hidden md:flex items-center gap-2 text-xs bg-indigo-950/40 border border-indigo-800/40 px-3 py-1.5 rounded-full">
                <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                <span className="text-indigo-200 capitalize font-medium">
                  {health.provider}: {health.model}
                </span>
              </div>
            )}

            {/* Mobile Workspace Toggle */}
            <button
              onClick={() => setShowMobileTree(!showMobileTree)}
              className="lg:hidden p-2 rounded-lg bg-slate-800 text-slate-300 hover:text-white"
              title="Toggle File Tree"
            >
              <FolderTree className="w-4 h-4" />
            </button>
          </div>
        </header>

        {/* Chat Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-6 md:px-8 space-y-6">
          {messages.length === 0 ? (
            <div className="max-w-2xl mx-auto mt-8 text-center space-y-6">
              <div className="w-16 h-16 mx-auto rounded-2xl bg-gradient-to-br from-indigo-500/20 to-purple-500/20 border border-indigo-500/30 flex items-center justify-center">
                <Bot className="w-8 h-8 text-indigo-400" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-white">
                  Welcome to AI Filesystem Manager
                </h2>
                <p className="text-sm text-slate-400 mt-2 max-w-lg mx-auto">
                  Type natural language requests below to create, read, update, or safely delete files.
                  Gemini translates your intent into Model Context Protocol (MCP) tool calls!
                </p>
              </div>

              {/* Quick Action Chips */}
              <div className="pt-2">
                <p className="text-xs uppercase tracking-wider font-semibold text-slate-500 mb-3">
                  Click a prompt to try it:
                </p>
                <div className="flex flex-wrap justify-center gap-2 max-w-xl mx-auto">
                  {QUICK_ACTIONS.map((prompt) => (
                    <button
                      key={prompt}
                      onClick={() => handleSendMessage(prompt)}
                      className="text-xs bg-slate-900 hover:bg-slate-800 border border-slate-800 hover:border-slate-700 text-slate-300 hover:text-white px-3.5 py-2 rounded-lg transition-all text-left shadow-sm flex items-center gap-1.5"
                    >
                      <span>{prompt}</span>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto space-y-6">
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex gap-3.5 ${
                    msg.role === 'user' ? 'justify-end' : 'justify-start'
                  }`}
                >
                  {msg.role === 'assistant' && (
                    <div className="w-8 h-8 rounded-lg bg-indigo-600/30 border border-indigo-500/40 flex items-center justify-center shrink-0 text-indigo-300 mt-1">
                      <Bot className="w-4 h-4" />
                    </div>
                  )}

                  <div
                    className={`max-w-[85%] rounded-2xl p-4 shadow-md ${
                      msg.role === 'user'
                        ? 'bg-indigo-600 text-white rounded-tr-none'
                        : 'bg-slate-900/90 border border-slate-800 text-slate-200 rounded-tl-none'
                    }`}
                  >
                    <div className="text-sm leading-relaxed whitespace-pre-wrap">
                      {msg.content}
                    </div>

                    {/* Render MCP Tool Badges */}
                    {msg.toolCalls && msg.toolCalls.length > 0 && (
                      <div className="mt-3 pt-3 border-t border-slate-800/80">
                        <div className="text-[11px] uppercase tracking-wider font-semibold text-slate-500 mb-1 flex items-center gap-1">
                          <Cpu className="w-3 h-3" /> MCP Tools Executed:
                        </div>
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

                    <div className="text-[10px] text-slate-500 mt-2 text-right">
                      {msg.timestamp}
                    </div>
                  </div>

                  {msg.role === 'user' && (
                    <div className="w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center shrink-0 text-slate-300 mt-1">
                      <User className="w-4 h-4" />
                    </div>
                  )}
                </div>
              ))}

              {loading && (
                <div className="flex items-center gap-3 text-slate-400 text-sm italic">
                  <div className="w-8 h-8 rounded-lg bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center text-indigo-400">
                    <Loader2 className="w-4 h-4 animate-spin" />
                  </div>
                  <span>Gemini is reasoning & calling MCP tools...</span>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input Bar */}
        <div className="border-t border-slate-800 p-4 bg-slate-900/60 backdrop-blur shrink-0">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSendMessage();
            }}
            className="max-w-3xl mx-auto flex items-center gap-2"
          >
            {messages.length > 0 && (
              <button
                type="button"
                onClick={() => setMessages([])}
                title="Clear Chat"
                className="p-3 text-slate-500 hover:text-slate-300 hover:bg-slate-800 rounded-xl transition-colors"
              >
                <Trash className="w-4 h-4" />
              </button>
            )}

            <div className="flex-1 relative">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask Gemini to create, read, update, or delete files..."
                disabled={loading}
                className="w-full bg-slate-950 border border-slate-800 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 text-white rounded-xl px-4 py-3 text-sm placeholder-slate-500 pr-10"
              />
            </div>

            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="px-4 py-3 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:hover:bg-indigo-600 text-white rounded-xl font-medium text-sm transition-all flex items-center gap-2 shadow-lg shadow-indigo-600/20 shrink-0"
            >
              <span>Send</span>
              <Send className="w-4 h-4" />
            </button>
          </form>
        </div>
      </div>

      {/* Right Pane: Live Workspace Explorer */}
      <div
        className={`w-80 shrink-0 fixed inset-y-0 right-0 z-20 lg:static lg:block transition-transform duration-300 ${
          showMobileTree ? 'translate-x-0' : 'translate-x-full lg:translate-x-0'
        }`}
      >
        <WorkspaceTree
          tree={tree}
          loading={treeLoading}
          onRefresh={fetchTree}
          onReset={handleResetWorkspace}
        />
      </div>
    </div>
  );
}

export default App;
