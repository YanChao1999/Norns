import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { apiClient } from '../api/client';
import { entryStageId, groupStages } from '../boardLayout';
import { BoardDetail, Card, Stage } from '../types';
import { AgentConfigModal } from './AgentConfig';
import { CardDrawer } from './CardDrawer';
import { CardHistory } from './CardHistory';
import { Column } from './Column';

interface Props {
  boardId: string;
  onEditMachine?: () => void;
}

export function Board({ boardId, onEditMachine }: Props) {
  const [selectedCard, setSelectedCard] = useState<Card | null>(null);
  const [historyCard, setHistoryCard] = useState<Card | null>(null);
  const [selectedStage, setSelectedStage] = useState<Stage | null>(null);

  const { data: board, isLoading } = useQuery({
    queryKey: ['board', boardId],
    queryFn: () => apiClient.get<BoardDetail>(`/boards/${boardId}`),
    refetchInterval: (query) => (query.state.data?.cards.some((card) => card.status === 'running' || card.status === 'waiting_join') ? 2000 : false)
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
  const entryId = entryStageId(stages);
  const rowCount = Math.max(1, ...stages.map((stage) => (stage.lane ?? 0) + 1));
  const liveCard = selectedCard ? (board.cards.find((item) => item.id === selectedCard.id) ?? selectedCard) : null;
  const liveHistoryCard = historyCard
    ? (board.cards.find((item) => item.id === historyCard.id) ?? historyCard)
    : null;

  if (liveHistoryCard) {
    return (
      <CardHistory
        card={liveHistoryCard}
        board={board}
        onBack={() => setHistoryCard(null)}
        onOpenCard={() => {
          setSelectedCard(liveHistoryCard);
          setHistoryCard(null);
        }}
      />
    );
  }

  return (
    <div>
      <div className="board-head">
        <div>
          <h1>{board.name}</h1>
          <p>{board.description || 'Each column is a workflow step. Cards follow the lines you draw. Column and row only place stages on the board.'}</p>
        </div>
        {onEditMachine ? (
          <button type="button" className="btn" onClick={onEditMachine}>
            Edit state machine
          </button>
        ) : null}
      </div>

      <div
        className="board-grid"
        style={{
          gridTemplateColumns: `64px repeat(${columns.length}, minmax(280px, 1fr))`,
          gridTemplateRows: `28px repeat(${rowCount}, minmax(240px, 1fr))`
        }}
      >
        <div className="board-grid-corner" />
        {columns.map((group, columnIndex) => {
          const parallel = group.length > 1;
          return (
            <header
              key={`col-${group[0].id}`}
              className={`board-column-banner${parallel ? ' is-parallel' : ''}`}
              style={{ gridColumn: columnIndex + 2, gridRow: 1 }}
            >
              <span>Column {group[0].order}</span>
              {parallel ? <span className="board-column-parallel">{group.length} rows in parallel</span> : null}
            </header>
          );
        })}
        {Array.from({ length: rowCount }, (_, index) => (
          <div key={`row-${index}`} className="board-row-label" style={{ gridColumn: 1, gridRow: index + 2 }}>
            Row {index + 1}
          </div>
        ))}
        {columns.flatMap((group, columnIndex) => {
          const parallel = group.length > 1;
          return Array.from({ length: rowCount }, (_, index) => {
            const row = index + 1;
            const stage = group.find((item) => (item.lane ?? 0) + 1 === row);
            if (!stage) {
              return (
                <div
                  key={`${group[0].id}-empty-${row}`}
                  className={`board-empty-cell${parallel ? ' is-parallel' : ''}`}
                  style={{ gridColumn: columnIndex + 2, gridRow: row + 1 }}
                />
              );
            }
            return (
              <div key={stage.id} className={`board-cell${parallel ? ' is-parallel' : ''}`} style={{ gridColumn: columnIndex + 2, gridRow: row + 1 }}>
                <Column
                  boardId={boardId}
                  stage={stage}
                  cards={cardsByStage.get(stage.id) ?? []}
                  isFirst={stage.id === entryId}
                  row={row}
                  parallel={parallel}
                  openCardId={liveCard?.id ?? null}
                  onOpenCard={setSelectedCard}
                  onOpenConfig={setSelectedStage}
                />
              </div>
            );
          });
        })}
      </div>

      <CardDrawer
        card={liveCard}
        board={board}
        onClose={() => setSelectedCard(null)}
        onOpenHistory={
          liveCard
            ? () => {
                setHistoryCard(liveCard);
                setSelectedCard(null);
              }
            : undefined
        }
      />
      <AgentConfigModal stage={selectedStage} onClose={() => setSelectedStage(null)} />
    </div>
  );
}
