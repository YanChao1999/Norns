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
  if (run.status === 'running' || run.status === 'pending' || run.status === 'waiting_tool') {
    return false;
  }
  return run.status === 'completed' || run.status === 'failed' || Boolean(run.completed_at);
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
  const stageRuns = runsForStage(runs, stageId);
  for (let index = stageRuns.length - 1; index >= 0; index -= 1) {
    if (isFinalizedRun(stageRuns[index])) {
      return stageRuns[index];
    }
  }
  return null;
}

export function safeHttpUrl(value: string): string | null {
  try {
    const url = new URL(value);
    if (url.protocol === 'http:' || url.protocol === 'https:') {
      return value;
    }
  } catch {
    /* not an absolute URL */
  }
  return null;
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

export function sandboxLabel(run: AgentRun | null | undefined): string {
  const sandbox = run?.inputs?.sandbox;
  if (!sandbox || typeof sandbox !== 'object') {
    return '';
  }
  const record = sandbox as Record<string, unknown>;
  const backend = String(record.backend || '').trim();
  const path = String(record.path || '').trim();
  if (!path || backend === 'none') {
    return '';
  }
  return backend ? `sandbox:${backend}` : 'sandbox';
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
  const current = currentIndex >= 0 ? stages[currentIndex] : undefined;

  return stages.map((stage) => {
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
    } else if (latestRun?.status === 'failed' && (currentIndex < 0 || (current && stage.order < current.order))) {
      state = 'failed';
    } else if (stageRuns.some((run) => run.status === 'completed')) {
      state = 'done';
    } else if (current && stage.order < current.order) {
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

export type StagePathKind = 'stage' | 'soft_join' | 'end';

export interface StagePathNode {
  id: string;
  kind: StagePathKind;
  label: string;
  state: JourneyStepState | 'locked' | 'waiting';
  parallel: boolean;
  stage?: Stage;
  step?: JourneyStep;
}

/** Flatten board columns into a stage-path with parallel markers and soft-join / end nodes. */
export function buildStagePath(card: Card, board: BoardDetail | undefined, runs: AgentRun[]): StagePathNode[] {
  const journey = buildJourney(card, board, runs);
  const byId = new Map(journey.map((step) => [step.stage.id, step]));
  const groups = groupStages(board?.stages ?? []);
  const nodes: StagePathNode[] = [];

  for (let index = 0; index < groups.length; index += 1) {
    const group = groups[index];
    const parallel = group.length > 1;
    for (const stage of [...group].sort((left, right) => (left.lane ?? 0) - (right.lane ?? 0))) {
      const step = byId.get(stage.id);
      nodes.push({
        id: stage.id,
        kind: 'stage',
        label: stage.name,
        state: step?.state ?? 'pending',
        parallel,
        stage,
        step
      });
    }

    const next = groups[index + 1];
    if (parallel && next) {
      const joinSettled = group.every((stage) => {
        const step = byId.get(stage.id);
        return step?.state === 'done' || step?.state === 'failed';
      });
      nodes.push({
        id: `soft-join-after-${group[0].id}`,
        kind: 'soft_join',
        label: 'soft join',
        state: joinSettled ? 'done' : card.status === 'waiting_join' || !joinSettled ? 'locked' : 'pending',
        parallel: false
      });
    }
  }

  const allDone = journey.length > 0 && journey.every((step) => step.state === 'done') && card.status === 'done';
  nodes.push({
    id: 'end',
    kind: 'end',
    label: 'End',
    state: allDone ? 'done' : 'pending',
    parallel: false
  });

  return nodes;
}

function groupStages(stages: Stage[]): Stage[][] {
  const sorted = [...stages].sort((left, right) => left.order - right.order || (left.lane ?? 0) - (right.lane ?? 0));
  const groups: Stage[][] = [];
  for (const stage of sorted) {
    const last = groups[groups.length - 1];
    if (last && last[0].order === stage.order) {
      last.push(stage);
    } else {
      groups.push([stage]);
    }
  }
  return groups;
}
