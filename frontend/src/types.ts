export interface DiffLine {
  type: 'context' | 'add' | 'delete';
  old_num?: number | null;
  new_num?: number | null;
  content: string;
}

export interface FileDiffData {
  file_path: string;
  stats: {
    added: number;
    deleted: number;
  };
  lines: DiffLine[];
}

export interface ToolCall {
  name: string;
  arguments: Record<string, any>;
  status: 'success' | 'error' | 'pending_confirmation' | 'cancelled';
  result?: string;
  diff?: FileDiffData;
}

export interface ConfirmationInfo {
  id: string;
  action: string;
  target: string;
  details?: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  toolCalls?: ToolCall[];
  confirmation?: ConfirmationInfo;
  timestamp: string;
  isStreaming?: boolean;
  currentStage?: 'thinking' | 'calling_tools' | 'generating' | 'done';
  stageMessage?: string;
  activeToolName?: string | null;
}

export interface FileNode {
  name: string;
  path: string;
  type: 'file' | 'directory';
  size?: number;
  children?: FileNode[];
}

export interface HealthInfo {
  status: string;
  provider: string;
  model: string;
  has_gemini_key: boolean;
  has_anthropic_key?: boolean;
  workspace: string;
  workspace_name?: string;
}
