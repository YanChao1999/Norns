import { describe, expect, it } from 'vitest';

import { Stage } from './types';
import { appendOperatorQuestion, boardWriteGateEnabled } from './writeGate';

function stage(partial: Partial<Stage> & Pick<Stage, 'id'>): Stage {
  return {
    board_id: 'b1',
    name: 'Stage',
    order: 1,
    require_approval: true,
    ...partial
  };
}

describe('boardWriteGateEnabled', () => {
  it('is false for empty boards', () => {
    expect(boardWriteGateEnabled([])).toBe(false);
    expect(boardWriteGateEnabled(null)).toBe(false);
  });

  it('is true when any stage confirms writes', () => {
    expect(
      boardWriteGateEnabled([
        stage({ id: 'a', confirm_writes: false }),
        stage({ id: 'b', confirm_writes: true })
      ])
    ).toBe(true);
  });

  it('is false when no stage confirms writes', () => {
    expect(boardWriteGateEnabled([stage({ id: 'a', confirm_writes: false })])).toBe(false);
  });
});

describe('appendOperatorQuestion', () => {
  it('appends a stamped operator question block', () => {
    const next = appendOperatorQuestion('Task body', 'Why was Polarion skipped?');
    expect(next).toContain('Task body');
    expect(next).toContain('## Operator question');
    expect(next).toContain('Why was Polarion skipped?');
  });

  it('ignores blank questions', () => {
    expect(appendOperatorQuestion('Task body', '   ')).toBe('Task body');
  });
});
