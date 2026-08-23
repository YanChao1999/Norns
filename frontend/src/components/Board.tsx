import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { apiClient } from '../api/client';
import { BoardDetail, Card, Stage } from '../types';
import { AgentConfigModal } from './AgentConfig';
import { CardDrawer } from './CardDrawer';
import { Column } from './Column';

interface Props {
  boardId: string;
  onEditMachine?: () => void;
}

export function Board({ boardId, onEditMachine }: Props) {
  const [selectedCard, setSelectedCard] = useState<Card | null>(null);
  const [selectedStage, setSelectedStage] = useState<Stage | null>(null);

  const { data: board, isLoading } = useQuery({
    queryKey: ['board', boardId],
    queryFn: () => apiClient.get<BoardDetail>(`/boards/${boardId}`),
    refetchInterval: (query) => (query.state.data?.cards.some((card) => card.status === 'running') ? 2000 : false)
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
    return <div className="muted">Loading board…</div>;
  }

  const stages = [...board.stages].sort((left, right) => left.order - right.order);
  const liveCard = selectedCard ? (board.cards.find((item) => item.id === selectedCard.id) ?? selectedCard) : null;

  return (
    <div>
      <div className="board-head">
        <div>
          <h1>{board.name}</h1>
          <p>{board.description || 'Isolated stage agents. Human gate between columns.'}</p>
        </div>
        {onEditMachine ? (
          <button type="button" className="btn" onClick={onEditMachine}>
            Edit state machine
          </button>
        ) : null}
      </div>

      <div className="board-columns">
        {stages.map((stage, index) => (
          <Column
            key={stage.id}
            boardId={boardId}
            stage={stage}
            cards={cardsByStage.get(stage.id) ?? []}
            isFirst={index === 0}
            openCardId={liveCard?.id ?? null}
            onOpenCard={setSelectedCard}
            onOpenConfig={setSelectedStage}
          />
        ))}
      </div>

      <CardDrawer card={liveCard} board={board} onClose={() => setSelectedCard(null)} />
      <AgentConfigModal stage={selectedStage} onClose={() => setSelectedStage(null)} />
    </div>
  );
}
