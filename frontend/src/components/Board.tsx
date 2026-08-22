import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '../api/client';
import { BoardDetail, Card, Stage } from '../types';
import { AgentConfigModal } from './AgentConfig';
import { CardDrawer } from './CardDrawer';
import { Column } from './Column';

interface Props {
  boardId: string;
}

export function Board({ boardId }: Props) {
  const queryClient = useQueryClient();
  const [selectedCard, setSelectedCard] = useState<Card | null>(null);
  const [selectedStage, setSelectedStage] = useState<Stage | null>(null);
  const [newCard, setNewCard] = useState({ title: '', body: '' });

  const { data: board, isLoading } = useQuery({
    queryKey: ['board', boardId],
    queryFn: () => apiClient.get<BoardDetail>(`/boards/${boardId}`),
    refetchInterval: (query) => (query.state.data?.cards.some((card) => card.status === 'running') ? 2000 : false)
  });

  const createCard = useMutation({
    mutationFn: async () => apiClient.post(`/boards/${boardId}/cards`, newCard),
    onSuccess: () => {
      setNewCard({ title: '', body: '' });
      queryClient.invalidateQueries({ queryKey: ['board', boardId] });
    }
  });

  const cardsByStage = useMemo(() => {
    const groups = new Map<string, Card[]>();
    board?.stages.forEach((stage) => groups.set(stage.id, []));
    board?.cards.forEach((card) => {
      if (card.current_stage_id && groups.has(card.current_stage_id)) {
        groups.get(card.current_stage_id)?.push(card);
      }
    });
    return groups;
  }, [board]);

  if (isLoading || !board) {
    return <div>Loading board…</div>;
  }

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ margin: 0 }}>{board.name}</h2>
          <p style={{ margin: '4px 0 0', color: '#6b7280' }}>{board.description || 'No description yet.'}</p>
        </div>
      </div>

      <section style={{ background: 'white', borderRadius: 12, padding: 16, border: '1px solid #e5e7eb' }}>
        <h3 style={{ marginTop: 0 }}>Add card</h3>
        <div style={{ display: 'grid', gap: 8 }}>
          <input
            placeholder="Card title"
            value={newCard.title}
            onChange={(event) => setNewCard((current) => ({ ...current, title: event.target.value }))}
          />
          <textarea
            placeholder="Markdown body"
            rows={4}
            value={newCard.body}
            onChange={(event) => setNewCard((current) => ({ ...current, body: event.target.value }))}
          />
          <button onClick={() => createCard.mutate()} disabled={!newCard.title || createCard.isPending}>
            {createCard.isPending ? 'Adding…' : 'Add card'}
          </button>
        </div>
      </section>

      <div style={{ display: 'flex', gap: 16, overflowX: 'auto', paddingBottom: 8 }}>
        {board.stages.map((stage) => (
          <Column
            key={stage.id}
            stage={stage}
            cards={cardsByStage.get(stage.id) ?? []}
            onOpenCard={setSelectedCard}
            onOpenConfig={setSelectedStage}
          />
        ))}
      </div>

      <CardDrawer
        card={selectedCard ? (board.cards.find((item) => item.id === selectedCard.id) ?? selectedCard) : null}
        onClose={() => setSelectedCard(null)}
      />
      <AgentConfigModal stage={selectedStage} onClose={() => setSelectedStage(null)} />
    </div>
  );
}
