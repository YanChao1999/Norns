import { describe, expect, it } from 'vitest';

import { buildJourney, chronologicalRuns, handoffSummary, isFinalizedRun } from './cardJourney';
import { AgentRun, BoardDetail, Card } from './types';

const board = {
  id: 'b1',
  name: 'Board',
  created_at: '',
  updated_at: '',
  stages: [
    { id: 's1', board_id: 'b1', name: 'Urd', order: 1, require_approval: true },
    { id: 's2', board_id: 'b1', name: 'Verdandi', order: 2, require_approval: true },
    { id: 's3', board_id: 'b1', name: 'Skuld', order: 3, require_approval: true }
  ],
  cards: []
} as BoardDetail;

function run(partial: Partial<AgentRun> & Pick<AgentRun, 'id' | 'stage_id'>): AgentRun {
  return {
    card_id: 'c1',
    inputs: {},
    tool_calls: [],
    model_output: '',
    handoff: {},
    status: 'completed',
    created_at: '2026-08-26T00:00:00Z',
    completed_at: '2026-08-26T00:01:00Z',
    ...partial
  };
}

describe('cardJourney', () => {
  it('orders runs oldest to newest', () => {
    const ordered = chronologicalRuns([
      run({ id: 'r2', stage_id: 's1', created_at: '2026-08-26T02:00:00Z' }),
      run({ id: 'r1', stage_id: 's1', created_at: '2026-08-26T01:00:00Z' })
    ]);
    expect(ordered.map((item) => item.id)).toEqual(['r1', 'r2']);
  });

  it('marks prior stages done and current stage here', () => {
    const card = {
      id: 'c1',
      board_id: 'b1',
      title: 'test',
      body: '',
      current_stage_id: 's2',
      status: 'waiting_approval'
    } as Card;
    const journey = buildJourney(card, board, [
      run({ id: 'r1', stage_id: 's1', handoff: { summary: 'from urd' } }),
      run({ id: 'r2', stage_id: 's2', handoff: { summary: 'from verdandi' } })
    ]);
    expect(journey.map((step) => [step.stage.name, step.state])).toEqual([
      ['Urd', 'done'],
      ['Verdandi', 'current'],
      ['Skuld', 'pending']
    ]);
  });

  it('reads handoff summary with model_output fallback', () => {
    expect(handoffSummary(run({ id: 'r1', stage_id: 's1', handoff: { summary: '  hi  ' } }))).toBe('hi');
    expect(handoffSummary(run({ id: 'r2', stage_id: 's1', model_output: 'log only' }))).toBe('log only');
    expect(isFinalizedRun(run({ id: 'r3', stage_id: 's1', status: 'running', completed_at: null, handoff: {} }))).toBe(
      false
    );
  });
});
