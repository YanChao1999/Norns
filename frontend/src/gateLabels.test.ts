import { describe, expect, it } from 'vitest';

import { approveLabel, conditionMatches, rejectLabel } from './gateLabels';
import { BoardDetail, Stage, StageTransition } from './types';

function stage(id: string, name: string, order: number, lane = 0): Stage {
  return { id, board_id: 'board', name, order, lane, require_approval: true };
}

function board(stages: Stage[]): BoardDetail {
  return { id: 'board', name: 'Board', created_at: '', updated_at: '', stages, cards: [] };
}

function edge(overrides: Partial<StageTransition> & Pick<StageTransition, 'to_stage_id'>): StageTransition {
  return {
    id: overrides.id ?? `e-${overrides.to_stage_id}`,
    board_id: 'board',
    from_stage_id: 'urd',
    event: 'approve',
    condition_key: '',
    condition_op: 'eq',
    condition_value: '',
    order: 0,
    ...overrides
  };
}

const stages = [stage('urd', 'Urd', 1), stage('tests', 'Unit tests', 2, 0), stage('software', 'Software', 2, 1), stage('skuld', 'Skuld', 3)];
const detail = board(stages);

describe('gate labels', () => {
  it('labels approve from the matching If line on the current handoff', () => {
    const lines = [
      edge({ to_stage_id: 'urd', condition_key: 'recommendation', condition_value: 'reject', order: 0 }),
      edge({ to_stage_id: 'skuld', order: 1 })
    ];
    expect(approveLabel(lines, detail, { recommendation: 'reject' })).toBe('Approve · Urd');
    expect(approveLabel(lines, detail, { recommendation: 'approve' })).toBe('Approve · Skuld');
  });

  it('does not let empty contains steal the default approve target', () => {
    const lines = [
      edge({ to_stage_id: 'tests', condition_key: 'summary', condition_op: 'contains', condition_value: '', order: 0 }),
      edge({ to_stage_id: 'skuld', order: 1 })
    ];
    expect(conditionMatches({ summary: 'anything' }, lines[0])).toBe(false);
    expect(approveLabel(lines, detail, { summary: 'anything' })).toBe('Approve · Skuld');
  });

  it('joins default parallel approve lines in the button label', () => {
    const lines = [edge({ to_stage_id: 'tests', order: 0 }), edge({ to_stage_id: 'software', order: 1 })];
    expect(approveLabel(lines, detail, {})).toBe('Approve · Unit tests + Software');
  });

  it('labels reject from the reject line that matches the handoff', () => {
    const lines = [
      edge({ to_stage_id: 'urd', event: 'reject', condition_key: 'risk', condition_value: 'high', order: 0 }),
      edge({ to_stage_id: 'tests', event: 'reject', order: 1 })
    ];
    expect(rejectLabel(lines, detail, { risk: 'high' })).toBe('Reject · Urd');
    expect(rejectLabel(lines, detail, { risk: 'low' })).toBe('Reject · Unit tests');
  });

  it('matches JSON true/false, not Python str(True)', () => {
    const line = edge({ to_stage_id: 'skuld', condition_key: 'ok', condition_value: 'true' });
    expect(conditionMatches({ ok: true }, line)).toBe(true);
    expect(conditionMatches({ ok: false }, line)).toBe(false);
  });

  it('keeps the generic approve label when only unmatched If lines exist', () => {
    const lines = [edge({ to_stage_id: 'urd', condition_key: 'risk', condition_value: 'high', order: 0 })];
    expect(approveLabel(lines, detail, { risk: 'low' })).toBe('Approve · next stage');
  });

  it('does not name a non-matching reject If as the destination', () => {
    const lines = [edge({ to_stage_id: 'urd', event: 'reject', condition_key: 'risk', condition_value: 'high', order: 0 })];
    expect(rejectLabel(lines, detail, { risk: 'low' })).toBe('Reject');
  });
});
