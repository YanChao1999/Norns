import { useEffect, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '../api/client';
import { STATUS_LABEL } from '../status';
import { AgentRun, BoardDetail, Card, StageTransition } from '../types';
import { Dialog } from './Dialog';

interface Props {
  card: Card | null;
  board?: BoardDetail;
  onClose: () => void;
}

interface Handoff {
  summary?: string;
  links?: string[];
  plantuml?: { svg?: string; source?: string };
  recommendation?: string;
  recommendation_reason?: string;
}

function agentRecommendation(value: unknown): 'approve' | 'reject' | null {
  return value === 'approve' || value === 'reject' ? value : null;
}

function isFinalizedRun(run: AgentRun): boolean {
  if (run.status === 'completed' || run.status === 'failed' || Boolean(run.completed_at)) {
    return true;
  }
  const handoff = (run.handoff ?? {}) as Handoff;
  return Boolean(handoff.summary || handoff.plantuml?.svg || (Array.isArray(handoff.links) && handoff.links.length));
}

export function CardDrawer({ card, board, onClose }: Props) {
  const queryClient = useQueryClient();
  const previousStatus = useRef<{ id?: string; status?: string }>({});
  const { data: runs = [] } = useQuery({
    enabled: Boolean(card),
    queryKey: ['runs', card?.id],
    queryFn: () => apiClient.get<AgentRun[]>(`/cards/${card?.id}/runs`),
    refetchInterval: card?.status === 'running' ? 2000 : false
  });

  useEffect(() => {
    const sameCard = previousStatus.current.id === card?.id;
    if (sameCard && previousStatus.current.status === 'running' && card?.status && card.status !== 'running') {
      void queryClient.invalidateQueries({ queryKey: ['runs', card.id] });
    }
    previousStatus.current = { id: card?.id, status: card?.status };
  }, [card?.id, card?.status, queryClient]);

  const approvalMutation = useMutation({
    mutationFn: async (approved: boolean) => {
      const latestHandoff = (runs.find(isFinalizedRun)?.handoff ?? {}) as Handoff;
      return apiClient.post(`/cards/${card?.id}/approve`, {
        approved,
        comment: gateComment(approved, agentRecommendation(latestHandoff.recommendation))
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['board', card?.board_id] });
      queryClient.invalidateQueries({ queryKey: ['runs', card?.id] });
      onClose();
    }
  });

  const runMutation = useMutation({
    mutationFn: async () => apiClient.post(`/cards/${card?.id}/run`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['board', card?.board_id] });
      queryClient.invalidateQueries({ queryKey: ['runs', card?.id] });
    }
  });

  if (!card) {
    return null;
  }

  const latestRun = runs[0];
  const handoffRun = runs.find(isFinalizedRun);
  const handoff = (handoffRun?.handoff ?? {}) as Handoff;
  const plantuml = handoff.plantuml?.svg;
  const canRun = card.status === 'idle' || card.status === 'blocked';
  const waiting = card.status === 'waiting_approval';
  const joining = card.status === 'waiting_join';
  const summary = handoff.summary || handoffRun?.model_output;
  const links = Array.isArray(handoff.links) ? handoff.links : [];
  const recommendation = agentRecommendation(handoff.recommendation);
  const recommendationReason = typeof handoff.recommendation_reason === 'string' ? handoff.recommendation_reason.trim() : '';
  const outgoing = (board?.transitions ?? []).filter((edge) => edge.from_stage_id === card.current_stage_id);
  const approveLines = outgoing.filter((edge) => edge.event === 'approve');
  const rejectLines = outgoing.filter((edge) => edge.event === 'reject');

  return (
    <Dialog open onClose={onClose} labelledBy="card-drawer-title" variant="drawer">
      <header className="drawer-head">
        <div>
          {card.external_id ? <p className="drawer-kicker">{card.external_id}</p> : null}
          <h2 id="card-drawer-title">{card.title}</h2>
        </div>
        <button type="button" className="btn btn-ghost" onClick={onClose}>
          Close
        </button>
      </header>

      <div className="drawer-body">
        <span className={`status status-${card.status}`}>{STATUS_LABEL[card.status]}</span>

        <section>
          <h3>Card body</h3>
          <p className="handoff">{card.body || 'No markdown body provided.'}</p>
        </section>

        {summary ? (
          <section>
            <h3>Handoff</h3>
            <p className="handoff">{summary}</p>
          </section>
        ) : (
          <section>
            <h3>Handoff</h3>
            <p className="muted">No stage run yet. Run this station to produce a handoff.</p>
          </section>
        )}

        {waiting && recommendation ? (
          <section className={`agent-decision is-${recommendation}`}>
            <h3>Agent recommendation</h3>
            <p className="handoff">
              {recommendation === 'approve' ? 'Approve' : 'Reject'}
              {recommendationReason ? ` — ${recommendationReason}` : ''}
            </p>
            <p className="muted">Advisory only. A human still has to confirm before the card moves.</p>
          </section>
        ) : null}

        {links.length ? (
          <section>
            <h3>Links</h3>
            <div className="links">
              {links.map((link) => (
                <a key={link} href={link} target="_blank" rel="noreferrer">
                  {link}
                </a>
              ))}
            </div>
          </section>
        ) : null}

        {latestRun ? (
          <section>
            <h3>Run log</h3>
            <pre className="log">{latestRun.model_output}</pre>
          </section>
        ) : null}

        {plantuml ? (
          <section>
            <h3>PlantUML preview</h3>
            <iframe
              sandbox=""
              srcDoc={`<!DOCTYPE html><html><head><meta charset="utf-8"><style>html,body{margin:0;background:#fff}</style></head><body>${plantuml}</body></html>`}
              title="PlantUML preview"
              className="preview-frame"
            />
          </section>
        ) : null}

        {latestRun ? (
          <details className="disclosure">
            <summary>Raw tool calls and handoff JSON</summary>
            <pre className="log">{JSON.stringify({ tool_calls: latestRun.tool_calls, handoff: latestRun.handoff }, null, 2)}</pre>
          </details>
        ) : null}
      </div>

      <footer className="drawer-foot">
        {canRun ? (
          <button type="button" className="btn btn-primary" onClick={() => runMutation.mutate()} disabled={runMutation.isPending}>
            {runMutation.isPending ? 'Starting…' : 'Run this stage'}
          </button>
        ) : null}
        {waiting ? (
          <>
            <button
              type="button"
              className={`btn btn-gate${recommendation === 'approve' ? ' is-recommended' : ''}`}
              onClick={() => approvalMutation.mutate(true)}
              disabled={approvalMutation.isPending}
              title={recommendation === 'approve' ? 'Agent recommended approve' : 'Confirm approve'}
            >
              {approveLabel(approveLines, board, handoff)}
              {recommendation === 'approve' ? ' · agent' : ''}
            </button>
            <button
              type="button"
              className={`btn btn-danger${recommendation === 'reject' ? ' is-recommended' : ''}`}
              onClick={() => approvalMutation.mutate(false)}
              disabled={approvalMutation.isPending}
              title={recommendation === 'reject' ? 'Agent recommended reject' : 'Confirm reject'}
            >
              {rejectLabel(rejectLines, board, handoff)}
              {recommendation === 'reject' ? ' · agent' : ''}
            </button>
          </>
        ) : null}
        {joining ? <span className="muted">This track is in. Waiting for the other parallel stages to finish, then they merge.</span> : null}
        {!canRun && !waiting && !joining ? <span className="muted">No gate action on this card.</span> : null}
      </footer>
    </Dialog>
  );
}

function targetName(board: BoardDetail | undefined, stageId: string | null): string {
  if (!stageId) {
    return 'Done';
  }
  return board?.stages.find((stage) => stage.id === stageId)?.name ?? 'stage';
}

function conditionMatches(handoff: Handoff, edge: StageTransition): boolean {
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

function approveLabel(lines: StageTransition[], board: BoardDetail | undefined, handoff: Handoff): string {
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

function rejectLabel(lines: StageTransition[], board: BoardDetail | undefined, handoff: Handoff): string {
  const shown = resolvedLines(lines, board, handoff, 'reject');
  const fallback = shown[0];
  if (!fallback) {
    return 'Reject';
  }
  return `Reject · ${targetName(board, fallback.to_stage_id)}`;
}

function gateComment(approved: boolean, recommendation: 'approve' | 'reject' | null): string {
  const action = approved ? 'Approved' : 'Rejected';
  if (!recommendation) {
    return `${action} in UI`;
  }
  const agreed = (approved && recommendation === 'approve') || (!approved && recommendation === 'reject');
  return agreed ? `${action} in UI (confirmed agent ${recommendation})` : `${action} in UI (overrode agent ${recommendation})`;
}
