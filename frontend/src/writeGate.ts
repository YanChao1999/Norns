import { Stage } from './types';

/** Board write-gate is on when any stage requires confirm-before-write. */
export function boardWriteGateEnabled(stages: Stage[] | undefined | null): boolean {
  if (!stages?.length) {
    return false;
  }
  return stages.some((stage) => Boolean(stage.confirm_writes));
}

export function appendOperatorQuestion(body: string, question: string): string {
  const trimmed = question.trim();
  if (!trimmed) {
    return body;
  }
  const stamp = new Date().toISOString();
  const block = `\n\n---\n## Operator question (${stamp})\n${trimmed}\n`;
  return `${body.trimEnd()}${block}`;
}
