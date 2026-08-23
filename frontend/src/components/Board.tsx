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

export function Board({ boardId, onEditMachine }: Props) {
  const [selectedCard, setSelectedCard] = useState<Card | null>(null);
  const [selectedStage, setSelectedStage] = useState<Stage | null>(null);

  const { data: board, isLoading } = useQuery({
    queryKey: ['board', boardId],
    queryFn: () => apiClient.get<BoardDetail>(`/boards/${boardId}`),
    refetchInterval: (query) =>
      query.state.data?.cards.some((card) => card.status === 'running' || card.status === 'waiting_join') ? 2000 : false
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

  const stages = [...board.stages].sort((left, right) => left.order - right.order || (left.lane ?? 0) - (right.lane ?? 0));
  const columns = groupStages(stages);
  const liveCard = selectedCard ? (board.cards.find((item) => item.id === selectedCard.id) ?? selectedCard) : null;

  return (
    <div>
      <div className="board-head">
        <div>
          <h1>{board.name}</h1>
          <p>
            {board.description || 'Each column is a workflow step. Same column, different row means those stages run in parallel.'}
          </p>
        </div>
        {onEditMachine ? (
          <button type="button" className="btn" onClick={onEditMachine}>
            Edit state machine
          </button>
        ) : null}
      </div>

      <div className="board-columns">
        {columns.map((group, columnIndex) => {
          const parallel = group.length > 1;
          return (
            <div key={group[0].id} className={`board-column-stack${parallel ? ' is-parallel' : ''}`}>
              <header className="board-column-banner">
                <span>Column {group[0].order}</span>
                {parallel ? <span className="board-column-parallel">{group.length} rows in parallel</span> : <span>Row 1</span>}
              </header>
              {group.map((stage, laneIndex) => (
                <Column
                  key={stage.id}
                  boardId={boardId}
                  stage={stage}
                  cards={cardsByStage.get(stage.id) ?? []}
                  isFirst={columnIndex === 0 && laneIndex === 0}
                  row={(stage.lane ?? 0) + 1}
                  parallel={parallel}
                  openCardId={liveCard?.id ?? null}
                  onOpenCard={setSelectedCard}
                  onOpenConfig={setSelectedStage}
                />
              ))}
            </div>
          );
        })}
      </div>

      <CardDrawer card={liveCard} board={board} onClose={() => setSelectedCard(null)} />
      <AgentConfigModal stage={selectedStage} onClose={() => setSelectedStage(null)} />
    </div>
  );
}
