import { describe, expect, it } from 'vitest';

import {
  buildJourney,
  buildStagePath,
  chronologicalRuns,
  compareRunDecision,
  handoffSummary,
  isFinalizedRun,
  latestFinalizedForStage,
  llmLabel,
  safeHttpUrl
} from './cardJourney';
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

  it('keeps waiting_tool_approval on the current stage, not a named column', () => {
    const card = {
      id: 'c1',
      board_id: 'b1',
      title: 'test',
      body: '',
      current_stage_id: 's3',
      status: 'waiting_tool_approval'
    } as Card;
    const journey = buildJourney(card, board, [
      run({ id: 'r1', stage_id: 's1', handoff: { summary: 'from urd' } }),
      run({ id: 'r2', stage_id: 's2', handoff: { summary: 'from verdandi' } }),
      run({ id: 'r3', stage_id: 's3', status: 'waiting_tool', completed_at: null, handoff: { summary: 'pending create' } })
    ]);
    expect(journey.map((step) => [step.stage.name, step.state])).toEqual([
      ['Urd', 'done'],
      ['Verdandi', 'done'],
      ['Skuld', 'current']
    ]);
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
    expect(isFinalizedRun(run({ id: 'r3', stage_id: 's1', status: 'running', completed_at: null, handoff: {} }))).toBe(false);
    expect(isFinalizedRun(run({ id: 'r4', stage_id: 's1', status: 'waiting_tool', completed_at: null, handoff: { summary: 'pending create' } }))).toBe(false);
  });

  it('uses the latest finalized run for a stage, not the oldest', () => {
    const oldest = run({
      id: 'r1',
      stage_id: 's1',
      created_at: '2026-08-26T01:00:00Z',
      handoff: { summary: 'old', recommendation: 'reject' }
    });
    const newest = run({
      id: 'r2',
      stage_id: 's1',
      created_at: '2026-08-26T03:00:00Z',
      handoff: { summary: 'new', recommendation: 'approve' }
    });
    expect(latestFinalizedForStage([newest, oldest], 's1')?.id).toBe('r2');
  });

  it('does not mark a parallel sibling lane as done by sort index', () => {
    const splitBoard = {
      ...board,
      stages: [
        { id: 's1', board_id: 'b1', name: 'Urd', order: 1, lane: 0, require_approval: true },
        { id: 's2a', board_id: 'b1', name: 'Tests', order: 2, lane: 0, require_approval: true },
        { id: 's2b', board_id: 'b1', name: 'Docs', order: 2, lane: 1, require_approval: true }
      ]
    } as BoardDetail;
    const card = {
      id: 'c1',
      board_id: 'b1',
      title: 'test',
      body: '',
      current_stage_id: 's2a',
      status: 'waiting_approval'
    } as Card;
    const journey = buildJourney(card, splitBoard, [
      run({ id: 'r1', stage_id: 's1', handoff: { summary: 'from urd' } }),
      run({ id: 'r2', stage_id: 's2a', handoff: { summary: 'tests' } })
    ]);
    expect(journey.map((step) => [step.stage.name, step.state])).toEqual([
      ['Urd', 'done'],
      ['Tests', 'current'],
      ['Docs', 'pending']
    ]);
  });

  it('only treats http(s) handoff links as URLs', () => {
    expect(safeHttpUrl('https://example.com/x')).toBe('https://example.com/x');
    expect(safeHttpUrl('javascript:alert(1)')).toBeNull();
  });

  it('compares reject reasons across reruns', () => {
    const first = run({
      id: 'r1',
      stage_id: 's1',
      handoff: { recommendation: 'reject', recommendation_reason: 'Jira connector is not attached.' }
    });
    const same = run({
      id: 'r2',
      stage_id: 's1',
      handoff: { recommendation: 'reject', recommendation_reason: 'jira connector is not attached.' }
    });
    const changed = run({
      id: 'r3',
      stage_id: 's1',
      handoff: { recommendation: 'reject', recommendation_reason: 'Missing project key.' }
    });
    expect(compareRunDecision(same, first)).toBe('same');
    expect(compareRunDecision(changed, first)).toBe('changed');
    expect(compareRunDecision(first, null)).toBe('first');
  });

  it('labels the LLM from the run handoff', () => {
    expect(
      llmLabel(
        run({
          id: 'r1',
          stage_id: 's1',
          handoff: { llm: { provider: 'deepseek', model: 'deepseek-v4-flash' } }
        })
      )
    ).toBe('DeepSeek · deepseek-v4-flash');
  });

  it('inserts soft join between parallel lanes and the next stage', () => {
    const parallelBoard = {
      ...board,
      stages: [
        { id: 's1', board_id: 'b1', name: 'Urd implement', order: 1, require_approval: true },
        { id: 's2a', board_id: 'b1', name: 'Check compliance', order: 2, lane: 0, require_approval: true },
        { id: 's2b', board_id: 'b1', name: 'Check requirements', order: 2, lane: 1, require_approval: true },
        { id: 's2c', board_id: 'b1', name: 'Run tests', order: 2, lane: 2, require_approval: false },
        { id: 's3', board_id: 'b1', name: 'Skuld confirm write', order: 3, require_approval: true, confirm_writes: true }
      ]
    } as BoardDetail;
    const card = {
      id: 'c1',
      board_id: 'b1',
      title: 'Checkout API',
      body: '',
      external_id: 'NOR-14',
      current_stage_id: 's2b',
      status: 'waiting_approval'
    } as Card;
    const path = buildStagePath(card, parallelBoard, [run({ id: 'r1', stage_id: 's1' }), run({ id: 'r2', stage_id: 's2a' })]);
    expect(path.map((node) => [node.kind, node.label, node.parallel])).toEqual([
      ['stage', 'Urd implement', false],
      ['stage', 'Check compliance', true],
      ['stage', 'Check requirements', true],
      ['stage', 'Run tests', true],
      ['soft_join', 'soft join', false],
      ['stage', 'Skuld confirm write', false],
      ['end', 'End', false]
    ]);
    expect(path.find((node) => node.kind === 'soft_join')?.state).toBe('locked');
  });
});
