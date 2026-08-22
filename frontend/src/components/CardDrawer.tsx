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

  if (!card) {
    return null;
  }

  const latestRun = runs[0];
  const plantuml = latestRun?.handoff?.plantuml?.svg as string | undefined;

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
              <div dangerouslySetInnerHTML={{ __html: plantuml }} />
            </div>
          ) : null}
        </>
      ) : (
        <div>No stage runs yet.</div>
      )}

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
