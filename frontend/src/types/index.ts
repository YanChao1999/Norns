export type CardStatus = 'idle' | 'running' | 'waiting_approval' | 'waiting_tool_approval' | 'waiting_join' | 'blocked' | 'done';
export type ConnectorType = 'openai' | 'cursor' | 'deepseek' | 'github' | 'jira' | 'polarion' | 'mcp' | 'workspace';

export interface AgentConfig {
  id: string;
  system_prompt: string;
  model: string;
  llm_provider?: string;
  temperature: number;
  tool_allowlist: string[];
  workspace_path?: string;
  git_url?: string;
}

export interface Stage {
  id: string;
  board_id: string;
  name: string;
  order: number;
  lane?: number;
  require_approval: boolean;
  confirm_writes?: boolean;
  auto_start?: boolean;
  agent_config?: AgentConfig | null;
}

export interface Card {
  id: string;
  board_id: string;
  title: string;
  body: string;
  external_id?: string | null;
  current_stage_id?: string | null;
  parent_card_id?: string | null;
  status: CardStatus;
  recommendation?: string | null;
  recommendation_reason?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface BoardSummary {
  id: string;
  name: string;
  description?: string | null;
  workspace_path?: string;
  git_url?: string;
  created_at: string;
  updated_at: string;
  stages: Stage[];
}

export interface StageTransition {
  id: string;
  board_id: string;
  from_stage_id: string;
  to_stage_id: string | null;
  event: 'approve' | 'reject' | 'auto';
  condition_key: string;
  condition_op: 'eq' | 'contains' | 'exists';
  condition_value: string;
  order: number;
}

export interface BoardDetail extends BoardSummary {
  cards: Card[];
  transitions?: StageTransition[];
}

export interface AgentRun {
  id: string;
  card_id: string;
  stage_id: string;
  inputs: Record<string, unknown>;
  tool_calls: Array<Record<string, unknown>>;
  model_output: string;
  handoff: Record<string, unknown>;
  status: string;
  created_at: string;
  completed_at?: string | null;
}

export interface Connector {
  id: string;
  name: string;
  connector_type: ConnectorType;
  is_active: boolean;
  config_keys: string[];
  public_config?: Record<string, string>;
}

export interface CardStatusMachine {
  states: CardStatus[];
  transitions: Partial<Record<CardStatus, CardStatus[]>>;
}
