import { useEffect, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '../api/client';
import { STATUS_LABEL } from '../status';
import { AgentRun, Card } from '../types';
import { Dialog } from './Dialog';

interface Props {
  card: Card | null;
  onClose: () => void;
}

interface Handoff {
  summary?: string;
  links?: string[];
  plantuml?: { svg?: string; source?: string };
}

function isFinalizedRun(run: AgentRun): boolean {
  if (run.status === 'completed' || run.status === 'failed' || Boolean(run.completed_at)) {
    return true;
  }
  const handoff = (run.handoff ?? {}) as Handoff;
  return Boolean(handoff.summary || handoff.plantuml?.svg || (Array.isArray(handoff.links) && handoff.links.length));
}

export function CardDrawer({ card, onClose }: Props) {
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
    mutationFn: async (approved: boolean) =>
      apiClient.post(`/cards/${card?.id}/approve`, {
        approved,
        comment: approved ? 'Approved in UI' : 'Rejected in UI'
      }),
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
  const summary = handoff.summary || handoffRun?.model_output;
  const links = Array.isArray(handoff.links) ? handoff.links : [];

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
              className="btn btn-gate"
              onClick={() => approvalMutation.mutate(true)}
              disabled={approvalMutation.isPending}
            >
              Approve · next stage
            </button>
            <button
              type="button"
              className="btn btn-danger"
              onClick={() => approvalMutation.mutate(false)}
              disabled={approvalMutation.isPending}
            >
              Reject
            </button>
          </>
        ) : null}
        {!canRun && !waiting ? <span className="muted">No gate action on this card.</span> : null}
      </footer>
    </Dialog>
  );
}
