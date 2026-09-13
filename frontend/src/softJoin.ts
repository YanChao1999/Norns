import { Card, Stage } from './types';

export interface SoftJoinProgress {
  settled: number;
  total: number;
  complete: boolean;
  waitingWriteCard: Card | null;
  joiningCards: Card[];
}

/** A lane is settled when it has a card that finished work or is waiting at a gate/join. */
function laneIsSettled(cards: Card[]): boolean {
  return cards.some((card) => ['done', 'waiting_join', 'waiting_tool_approval', 'waiting_approval'].includes(card.status));
}

/** Count how many parallel lanes have a settled (or join-waiting) card. */
export function softJoinProgress(parallelStages: Stage[], cards: Card[]): SoftJoinProgress {
  const total = parallelStages.length;
  let settled = 0;
  const joiningCards: Card[] = [];
  let waitingWriteCard: Card | null = null;

  for (const stage of parallelStages) {
    const stageCards = cards.filter((card) => card.current_stage_id === stage.id);
    for (const card of stageCards) {
      if (card.status === 'waiting_join') {
        joiningCards.push(card);
      }
      if (card.status === 'waiting_tool_approval') {
        waitingWriteCard = waitingWriteCard ?? card;
      }
    }
    if (laneIsSettled(stageCards)) {
      settled += 1;
    }
  }

  // Parent/join cards that left parallel stages and sit on a join/confirm stage.
  const outside = cards.filter(
    (card) => (card.status === 'waiting_join' || card.status === 'waiting_tool_approval') && !parallelStages.some((stage) => stage.id === card.current_stage_id)
  );
  for (const card of outside) {
    if (card.status === 'waiting_join') {
      joiningCards.push(card);
    }
    if (card.status === 'waiting_tool_approval') {
      waitingWriteCard = waitingWriteCard ?? card;
    }
  }

  return {
    settled: Math.min(settled, total),
    total,
    complete: total > 0 && settled >= total,
    waitingWriteCard,
    joiningCards
  };
}

export function boardHasParallel(groups: Stage[][]): boolean {
  return groups.some((group) => group.length > 1);
}
