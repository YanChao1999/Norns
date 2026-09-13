import { AgentRun } from './types';

export const IN_PROGRESS_HINT = 'This stage is in progress. Wait for the handoff — extra Run clicks are ignored until it finishes.';

export const NO_API_KEY_HINT =
  'No usable model connector yet, so runs are practice only. Add DeepSeek, OpenAI, or Cursor in Settings before expecting a real agent.';

export const PLACEHOLDER_RUN_HINT =
  'This handoff is a practice run — no usable API key was configured. Approving here only moves the practice card; add a connector in Settings for a real model.';

export const PRACTICE_WAITING_HINT = 'Practice run — confirm to continue (not a real model handoff)';

export const PRACTICE_APPROVE_LABEL = 'Practice approve';
export const PRACTICE_REJECT_LABEL = 'Practice reject';

export function isPlaceholderRun(run: Pick<AgentRun, 'model_output' | 'handoff'> | undefined): boolean {
  if (!run) {
    return false;
  }
  const handoff = run.handoff ?? {};
  if (handoff.placeholder === true) {
    return true;
  }
  const summary = typeof handoff.summary === 'string' ? handoff.summary : '';
  return /practice run|api key not configured|no openai api key/i.test(`${run.model_output} ${summary}`);
}
