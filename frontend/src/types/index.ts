export type CardStatus = 'idle' | 'running' | 'waiting_approval' | 'blocked' | 'done';
export type ConnectorType = 'github' | 'jira' | 'polarion';

export interface AgentConfig {
  id: string;
  system_prompt: string;
  model: string;
  temperature: number;
  tool_allowlist: string[];
}

export interface Stage {
  id: string;
  board_id: string;
  name: string;
  order: number;
  require_approval: boolean;
  agent_config?: AgentConfig | null;
}

export interface Card {
  id: string;
  board_id: string;
  title: string;
  body: string;
  external_id?: string | null;
  current_stage_id?: string | null;
  status: CardStatus;
  created_at?: string;
  updated_at?: string;
}

export interface BoardSummary {
  id: string;
  name: string;
  description?: string | null;
  created_at: string;
  updated_at: string;
  stages: Stage[];
}

export interface BoardDetail extends BoardSummary {
  cards: Card[];
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
}
