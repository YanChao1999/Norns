import { BoardDetail, StageTransition } from './types';

export interface Handoff {
  summary?: string;
  links?: string[];
  plantuml?: { svg?: string; source?: string };
  recommendation?: string;
  recommendation_reason?: string;
  [key: string]: unknown;
}

export function approveLabel(lines: StageTransition[], board: BoardDetail | undefined, handoff: Handoff): string {
  const shown = resolvedLines(lines, board, handoff, 'approve');
  if (shown.length > 1) {
    return `Approve · ${shown.map((edge) => targetName(board, edge.to_stage_id)).join(' + ')}`;
  }
  const fallback = shown[0] ?? lines[0];
  if (!fallback) {
    return 'Approve · next stage';
  }
  return `Approve · ${targetName(board, fallback.to_stage_id)}`;
}

export function rejectLabel(lines: StageTransition[], board: BoardDetail | undefined, handoff: Handoff): string {
  const shown = resolvedLines(lines, board, handoff, 'reject');
  const fallback = shown[0];
  if (!fallback) {
    return 'Reject';
  }
  return `Reject · ${targetName(board, fallback.to_stage_id)}`;
}

function targetName(board: BoardDetail | undefined, stageId: string | null): string {
  if (!stageId) {
    return 'Done';
  }
  return board?.stages.find((stage) => stage.id === stageId)?.name ?? 'stage';
}

export function conditionMatches(handoff: Handoff, edge: StageTransition): boolean {
  let current: unknown = handoff;
  for (const part of edge.condition_key.split('.')) {
    if (!current || typeof current !== 'object' || !(part in current)) {
      current = undefined;
      break;
    }
    current = (current as Record<string, unknown>)[part];
  }
  const op = edge.condition_op || 'eq';
  if (op === 'exists') {
    return current !== undefined && current !== null;
  }
  const text = current == null ? '' : String(current);
  const value = edge.condition_value;
  if (op === 'contains') {
    if (!value) {
      return false;
    }
    return text.toLowerCase().includes(value.toLowerCase());
  }
  return text === value;
}

function resolvedLines(lines: StageTransition[], board: BoardDetail | undefined, handoff: Handoff, event: 'approve' | 'reject'): StageTransition[] {
  const matching = [...lines].sort((left, right) => left.order - right.order);
  const conditioned = matching.filter((edge) => edge.condition_key.trim());
  const defaults = matching.filter((edge) => !edge.condition_key.trim());
  const matchedIfs = conditioned.filter((edge) => conditionMatches(handoff, edge));
  if (event === 'reject') {
    const chosen = matchedIfs[0] ?? defaults[0] ?? matching[0];
    return chosen ? [chosen] : [];
  }
  if (matchedIfs.length) {
    return matchedIfs;
  }
  const forward = defaults.filter((edge) => isForwardLine(board, edge));
  return forward.length ? forward : defaults;
}

function isForwardLine(board: BoardDetail | undefined, edge: StageTransition): boolean {
  if (!edge.to_stage_id) {
    return true;
  }
  const from = board?.stages.find((stage) => stage.id === edge.from_stage_id);
  const to = board?.stages.find((stage) => stage.id === edge.to_stage_id);
  if (!from || !to) {
    return true;
  }
  return to.order > from.order;
}
