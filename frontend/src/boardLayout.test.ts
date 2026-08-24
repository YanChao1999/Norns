import { describe, expect, it } from 'vitest';

import { entryStageId, groupStages } from './boardLayout';
import { Stage } from './types';

function stage(id: string, order: number, lane = 0): Stage {
  return { id, board_id: 'board', name: id, order, lane, require_approval: true };
}

describe('entryStageId', () => {
  it('puts Add-card on the first real stage even when that stage is not row 1', () => {
    const stages = [stage('verdandi', 2), stage('urd', 1, 2)];
    expect(entryStageId(stages)).toBe('urd');
    expect(groupStages(stages)[0][0].lane).toBe(2);
  });

  it('uses the lowest lane in the first column when the first column is parallel', () => {
    const stages = [stage('tests', 1, 1), stage('software', 1, 0), stage('join', 2)];
    expect(entryStageId(stages)).toBe('software');
  });

  it('never treats a later column as the entry station', () => {
    const stages = [stage('urd', 1), stage('verdandi', 2, 0), stage('skuld', 3)];
    expect(entryStageId(stages)).toBe('urd');
  });
});
