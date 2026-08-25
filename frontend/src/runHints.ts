import { AgentRun } from './types';

export const IN_PROGRESS_HINT =
  'This stage is in progress. Wait for the handoff — extra Run clicks are ignored until it finishes.';

export const NO_API_KEY_HINT =
  'No model connector yet, so runs are practice only (no model is called). Open Settings, add OpenAI, Cursor, or DeepSeek with your API key, then run the stage again.';

export const PLACEHOLDER_RUN_HINT =
  'This handoff is a practice run because no API key was configured. Add an OpenAI, Cursor, or DeepSeek connector in Settings and run the stage again for a real agent.';

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
