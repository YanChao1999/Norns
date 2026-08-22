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
  const [draggedCard, setDraggedCard] = useState<Card | null>(null);
  const [newCard, setNewCard] = useState({ title: '', body: '' });

  const { data: board, isLoading } = useQuery({
    queryKey: ['board', boardId],
    queryFn: () => apiClient.get<BoardDetail>(`/boards/${boardId}`)
  });

  const createCard = useMutation({
    mutationFn: async () => apiClient.post(`/boards/${boardId}/cards`, newCard),
    onSuccess: () => {
      setNewCard({ title: '', body: '' });
      queryClient.invalidateQueries({ queryKey: ['board', boardId] });
    }
  });

  const moveCard = useMutation({
    mutationFn: async ({ cardId, stageId }: { cardId: string; stageId: string }) =>
      apiClient.put(`/cards/${cardId}`, { current_stage_id: stageId }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['board', boardId] })
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

  const handleDrop = (stage: Stage) => {
    if (!board || !draggedCard || draggedCard.status === 'waiting_approval') {
      return;
    }
    const currentIndex = board.stages.findIndex((item) => item.id === draggedCard.current_stage_id);
    const targetIndex = board.stages.findIndex((item) => item.id === stage.id);
    if (Math.abs(targetIndex - currentIndex) > 1) {
      return;
    }
    moveCard.mutate({ cardId: draggedCard.id, stageId: stage.id });
    setDraggedCard(null);
  };

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
            onDropCard={handleDrop}
            onDragStart={setDraggedCard}
          />
        ))}
      </div>

      <CardDrawer card={selectedCard} onClose={() => setSelectedCard(null)} />
      <AgentConfigModal stage={selectedStage} onClose={() => setSelectedStage(null)} />
    </div>
  );
}
