import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '../api/client';
import { Handoff, approveLabel, rejectLabel } from '../gateLabels';
import { IN_PROGRESS_HINT, PLACEHOLDER_RUN_HINT, isPlaceholderRun } from '../runHints';
import { STATUS_LABEL } from '../status';
import { AgentRun, BoardDetail, Card } from '../types';
import { Dialog } from './Dialog';

interface Props {
  card: Card | null;
  board?: BoardDetail;
  onClose: () => void;
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
  const [runStarted, setRunStarted] = useState(false);
  const { data: runs = [] } = useQuery({
    enabled: Boolean(card),
    queryKey: ['runs', card?.id],
    queryFn: () => apiClient.get<AgentRun[]>(`/cards/${card?.id}/runs`),
    refetchInterval: card?.status === 'running' ? 2000 : false
  });

  useEffect(() => {
    setRunStarted(false);
  }, [card?.id, card?.status]);

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
    },
    onError: (error) => {
      queryClient.invalidateQueries({ queryKey: ['board', card?.board_id] });
      queryClient.invalidateQueries({ queryKey: ['runs', card?.id] });
      if (!runErrorMessage(error).includes('already running')) {
        setRunStarted(false);
      }
    }
  });

  if (!card) {
    return null;
  }

  const latestRun = runs[0];
  const handoffRun = runs.find(isFinalizedRun);
  const handoff = (handoffRun?.handoff ?? {}) as Handoff;
  const plantuml = handoff.plantuml?.svg;
  const inProgress = card.status === 'running' || runStarted;
  const canRun = (card.status === 'idle' || card.status === 'blocked') && !runStarted;
  const waiting = card.status === 'waiting_approval';
  const joining = card.status === 'waiting_join';
  const placeholderRun = isPlaceholderRun(handoffRun ?? latestRun);
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

        {inProgress ? (
          <p className="notice" role="status">
            {IN_PROGRESS_HINT}
          </p>
        ) : null}
        {placeholderRun && !inProgress ? (
          <p className="notice" role="status">
            {PLACEHOLDER_RUN_HINT}
          </p>
        ) : null}

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
        {runMutation.isError ? <div className="error">{runErrorMessage(runMutation.error)}</div> : null}
      </div>

      <footer className="drawer-foot">
        {canRun ? (
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              setRunStarted(true);
              runMutation.mutate();
            }}
            disabled={runMutation.isPending || runStarted}
          >
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
        {inProgress ? <span className="muted">Agent is running this stage…</span> : null}
        {!canRun && !waiting && !joining && !inProgress ? <span className="muted">No gate action on this card.</span> : null}
      </footer>
    </Dialog>
  );
}

function runErrorMessage(error: unknown): string {
  if (!(error instanceof Error)) {
    return 'Could not start this stage.';
  }
  try {
    const parsed = JSON.parse(error.message) as { detail?: unknown };
    if (typeof parsed.detail === 'string' && parsed.detail.trim()) {
      return parsed.detail;
    }
  } catch {
    /* response body was not JSON */
  }
  return error.message || 'Could not start this stage.';
}

function gateComment(approved: boolean, recommendation: 'approve' | 'reject' | null): string {
  const action = approved ? 'Approved' : 'Rejected';
  if (!recommendation) {
    return `${action} in UI`;
  }
  const agreed = (approved && recommendation === 'approve') || (!approved && recommendation === 'reject');
  return agreed ? `${action} in UI (confirmed agent ${recommendation})` : `${action} in UI (overrode agent ${recommendation})`;
}
