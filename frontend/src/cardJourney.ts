import { Handoff } from './gateLabels';
import { AgentRun, BoardDetail, Card, Stage } from './types';

export type JourneyStepState = 'done' | 'current' | 'pending' | 'failed' | 'running';

export interface JourneyStep {
  stage: Stage;
  state: JourneyStepState;
  runs: AgentRun[];
  latestRun: AgentRun | null;
}

export function diagramSvg(handoff: Handoff): string | undefined {
  const svg = handoff.plantuml?.svg;
  return typeof svg === 'string' && svg.trim() ? svg : undefined;
}

export function isFinalizedRun(run: AgentRun): boolean {
  if (run.status === 'completed' || run.status === 'failed' || Boolean(run.completed_at)) {
    return true;
  }
  const handoff = (run.handoff ?? {}) as Handoff;
  return Boolean(handoff.summary || diagramSvg(handoff) || (Array.isArray(handoff.links) && handoff.links.length));
}

export function stageName(board: BoardDetail | undefined, stageId: string): string {
  return board?.stages.find((stage) => stage.id === stageId)?.name ?? 'Unknown stage';
}

export function orderedStages(board: BoardDetail | undefined): Stage[] {
  return [...(board?.stages ?? [])].sort((left, right) => left.order - right.order || (left.lane ?? 0) - (right.lane ?? 0));
}

/** Oldest → newest for reading the card’s path. */
export function chronologicalRuns(runs: AgentRun[]): AgentRun[] {
  return [...runs].sort((left, right) => left.created_at.localeCompare(right.created_at));
}

export function runsForStage(runs: AgentRun[], stageId: string): AgentRun[] {
  return chronologicalRuns(runs.filter((run) => run.stage_id === stageId));
}

export function latestFinalizedForStage(runs: AgentRun[], stageId: string): AgentRun | null {
  return runs.filter((run) => run.stage_id === stageId).find(isFinalizedRun) ?? null;
}

export function handoffSummary(run: AgentRun | null | undefined): string {
  if (!run) {
    return '';
  }
  const handoff = (run.handoff ?? {}) as Handoff;
  if (typeof handoff.summary === 'string' && handoff.summary.trim()) {
    return handoff.summary.trim();
  }
  return (run.model_output || '').trim();
}

export function normalizeReason(text: string): string {
  return text.toLowerCase().replace(/\s+/g, ' ').trim();
}

export function runDecision(run: AgentRun | null | undefined): { recommendation: string; reason: string } {
  if (!run) {
    return { recommendation: '', reason: '' };
  }
  const handoff = (run.handoff ?? {}) as Handoff;
  const recommendation = typeof handoff.recommendation === 'string' ? handoff.recommendation.trim().toLowerCase() : '';
  const reason = typeof handoff.recommendation_reason === 'string' && handoff.recommendation_reason.trim() ? handoff.recommendation_reason.trim() : '';
  return { recommendation, reason };
}

export type ReasonCompare = 'first' | 'same' | 'changed';

export function compareRunDecision(current: AgentRun, previous: AgentRun | null | undefined): ReasonCompare {
  if (!previous) {
    return 'first';
  }
  const now = runDecision(current);
  const before = runDecision(previous);
  if (!now.recommendation && !now.reason) {
    return 'first';
  }
  if (now.recommendation === before.recommendation && normalizeReason(now.reason) === normalizeReason(before.reason) && now.reason) {
    return 'same';
  }
  return 'changed';
}

export function llmLabel(run: AgentRun | null | undefined): string {
  const source = run?.handoff?.llm ?? run?.inputs?.llm;
  if (!source || typeof source !== 'object') {
    return '';
  }
  const record = source as Record<string, unknown>;
  const provider = String(record.provider || '').trim();
  const model = String(record.model || '').trim();
  const names: Record<string, string> = { openai: 'OpenAI', deepseek: 'DeepSeek', cursor: 'Cursor' };
  const label = names[provider] || (provider ? provider[0].toUpperCase() + provider.slice(1) : '');
  return [label, model].filter(Boolean).join(' · ');
}

export function pluginsSnapshot(run: AgentRun | null | undefined): { allowlist: string[]; attached: string[]; jiraConnector: boolean | null } {
  const plugins = run?.inputs?.plugins;
  if (!plugins || typeof plugins !== 'object') {
    return { allowlist: [], attached: [], jiraConnector: null };
  }
  const record = plugins as Record<string, unknown>;
  const allowlist = Array.isArray(record.allowlist) ? record.allowlist.map((item) => String(item)) : [];
  const mcp = Array.isArray(record.mcp_servers) ? record.mcp_servers.map((item) => String(item)) : [];
  const tools = Array.isArray(record.tools) ? record.tools.map((item) => String(item)) : [];
  const attached = mcp.length ? mcp : tools;
  const jiraConnector = typeof record.jira_connector === 'boolean' ? record.jira_connector : null;
  return { allowlist, attached, jiraConnector };
}

export function formatRunTime(value: string | null | undefined): string {
  if (!value) {
    return '';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });
}

export function buildJourney(card: Card, board: BoardDetail | undefined, runs: AgentRun[]): JourneyStep[] {
  const stages = orderedStages(board);
  const currentId = card.current_stage_id ?? '';
  const currentIndex = stages.findIndex((stage) => stage.id === currentId);

  return stages.map((stage, index) => {
    const stageRuns = runsForStage(runs, stage.id);
    const latestRun = stageRuns.length ? stageRuns[stageRuns.length - 1] : null;
    let state: JourneyStepState = 'pending';

    if (stage.id === currentId) {
      if (latestRun?.status === 'running' || card.status === 'running') {
        state = 'running';
      } else if (latestRun?.status === 'failed') {
        state = 'failed';
      } else {
        state = 'current';
      }
    } else if (latestRun?.status === 'failed' && (currentIndex < 0 || index < currentIndex)) {
      state = 'failed';
    } else if (stageRuns.some((run) => run.status === 'completed' || isFinalizedRun(run))) {
      state = 'done';
    } else if (currentIndex >= 0 && index < currentIndex) {
      state = 'done';
    } else if (latestRun?.status === 'running') {
      state = 'running';
    }

    return { stage, state, runs: stageRuns, latestRun };
  });
}

export function journeyStateLabel(state: JourneyStepState): string {
  switch (state) {
    case 'done':
      return 'done';
    case 'current':
      return 'here';
    case 'pending':
      return 'pending';
    case 'failed':
      return 'failed';
    case 'running':
      return 'running';
  }
}
