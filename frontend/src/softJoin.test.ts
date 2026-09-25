import { describe, expect, it } from 'vitest';

import { boardHasParallel, softJoinProgress } from './softJoin';
import { Card, Stage } from './types';

function stage(partial: Partial<Stage> & Pick<Stage, 'id' | 'name' | 'order'>): Stage {
  return {
    board_id: 'b1',
    require_approval: false,
    lane: 0,
    ...partial
  };
}

function card(partial: Partial<Card> & Pick<Card, 'id' | 'status' | 'current_stage_id'>): Card {
  return {
    board_id: 'b1',
    title: 'Card',
    body: '',
    ...partial
  };
}

describe('softJoinProgress', () => {
  const lanes = [
    stage({ id: 'a', name: 'A', order: 2, lane: 0 }),
    stage({ id: 'b', name: 'B', order: 2, lane: 1 }),
    stage({ id: 'c', name: 'C', order: 2, lane: 2 })
  ];

  it('counts settled lanes and exposes waiting write cards', () => {
    const cards = [
      card({ id: '1', status: 'done', current_stage_id: 'a' }),
      card({ id: '2', status: 'waiting_approval', current_stage_id: 'b' }),
      card({ id: '3', status: 'running', current_stage_id: 'c' })
    ];
    const progress = softJoinProgress(lanes, cards);
    expect(progress.settled).toBe(2);
    expect(progress.total).toBe(3);
    expect(progress.complete).toBe(false);
  });

  it('is complete when every lane is settled', () => {
    const cards = [
      card({ id: '1', status: 'waiting_join', current_stage_id: 'a' }),
      card({ id: '2', status: 'waiting_join', current_stage_id: 'b' }),
      card({ id: '3', status: 'waiting_tool_approval', current_stage_id: 'c' })
    ];
    const progress = softJoinProgress(lanes, cards);
    expect(progress.complete).toBe(true);
    expect(progress.waitingWriteCard?.id).toBe('3');
    expect(progress.joiningCards).toHaveLength(2);
  });
});

describe('boardHasParallel', () => {
  it('detects multi-lane column groups', () => {
    expect(boardHasParallel([[stage({ id: 'a', name: 'A', order: 1 })]])).toBe(false);
    expect(
      boardHasParallel([
        [stage({ id: 'a', name: 'A', order: 1 })],
        [stage({ id: 'b', name: 'B', order: 2, lane: 0 }), stage({ id: 'c', name: 'C', order: 2, lane: 1 })]
      ])
    ).toBe(true);
  });
});
