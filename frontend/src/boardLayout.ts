import { Stage } from './types';

export function groupStages(stages: Stage[]): Stage[][] {
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

export function entryStageId(stages: Stage[]): string | undefined {
  return groupStages(stages)[0]?.[0]?.id;
}
