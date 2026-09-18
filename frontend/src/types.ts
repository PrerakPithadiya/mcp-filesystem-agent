export interface ToolCall {
  name: string;
  arguments: Record<string, any>;
  status: 'success' | 'error' | 'pending_confirmation' | 'cancelled';
  result?: string;
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
}
