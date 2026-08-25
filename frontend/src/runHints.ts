import { AgentRun } from './types';

export const IN_PROGRESS_HINT =
  'This stage is in progress. Wait for the handoff — extra Run clicks are ignored until it finishes.';

export const NO_API_KEY_HINT =
  'No usable model connector yet, so runs are practice only. Open Settings and add DeepSeek, OpenAI, or Cursor.';

export const PLACEHOLDER_RUN_HINT =
  'This handoff is a practice run because no usable API key was configured. Add a DeepSeek, OpenAI, or Cursor connector in Settings and run the stage again.';

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
