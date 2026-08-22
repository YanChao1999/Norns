import type { CSSProperties } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '../api/client';
import { AgentRun, Card } from '../types';

interface Props {
  card: Card | null;
  onClose: () => void;
}

export function CardDrawer({ card, onClose }: Props) {
  const queryClient = useQueryClient();
  const { data: runs = [] } = useQuery({
    enabled: Boolean(card),
    queryKey: ['runs', card?.id],
    queryFn: () => apiClient.get<AgentRun[]>(`/cards/${card?.id}/runs`)
  });

  const approvalMutation = useMutation({
    mutationFn: async (approved: boolean) =>
      apiClient.post(`/cards/${card?.id}/approve`, { approved, comment: approved ? 'Approved in UI' : 'Rejected in UI' }),
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
  const plantuml = latestRun?.handoff?.plantuml?.svg as string | undefined;
  const canRun = card.status === 'idle' || card.status === 'blocked';

  return (
    <aside style={drawerStyle}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ marginTop: 0 }}>{card.title}</h2>
        <button onClick={onClose}>Close</button>
      </div>
      <div style={{ color: '#6b7280', marginBottom: 12 }}>{card.status.replace('_', ' ')}</div>
      <pre style={preStyle}>{card.body || 'No markdown body provided.'}</pre>

      {latestRun ? (
        <>
          <h3>Current run log</h3>
          <pre style={preStyle}>{latestRun.model_output}</pre>
          <h3>Tool calls</h3>
          <pre style={preStyle}>{JSON.stringify(latestRun.tool_calls, null, 2)}</pre>
          <h3>Handoff</h3>
          <pre style={preStyle}>{JSON.stringify(latestRun.handoff, null, 2)}</pre>
          {plantuml ? (
            <div>
              <h3>PlantUML preview</h3>
              <iframe
                sandbox=""
                srcDoc={`<!DOCTYPE html><html><head><meta charset="utf-8"><style>html,body{margin:0;background:#fff}</style></head><body>${plantuml}</body></html>`}
                title="PlantUML preview"
                style={previewFrameStyle}
              />
            </div>
          ) : null}
        </>
      ) : (
        <div>No stage runs yet.</div>
      )}

      {canRun ? (
        <div style={{ marginTop: 12 }}>
          <button onClick={() => runMutation.mutate()} disabled={runMutation.isPending}>
            {runMutation.isPending ? 'Starting…' : 'Run this stage'}
          </button>
        </div>
      ) : null}

      {card.status === 'waiting_approval' ? (
        <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
          <button onClick={() => approvalMutation.mutate(true)} disabled={approvalMutation.isPending}>
            Approve
          </button>
          <button onClick={() => approvalMutation.mutate(false)} disabled={approvalMutation.isPending}>
            Reject
          </button>
        </div>
      ) : null}
    </aside>
  );
}

const drawerStyle: CSSProperties = {
  position: 'fixed',
  top: 0,
  right: 0,
  width: 'min(560px, 92vw)',
  height: '100vh',
  overflowY: 'auto',
  background: 'white',
  boxShadow: '-4px 0 24px rgba(0,0,0,0.12)',
  padding: 24,
  zIndex: 30
};

const preStyle: CSSProperties = {
  whiteSpace: 'pre-wrap',
  background: '#111827',
  color: '#f9fafb',
  padding: 12,
  borderRadius: 8,
  fontSize: 13
};

const previewFrameStyle: CSSProperties = {
  width: '100%',
  minHeight: 220,
  border: '1px solid #e5e7eb',
  borderRadius: 8,
  background: 'white'
};
