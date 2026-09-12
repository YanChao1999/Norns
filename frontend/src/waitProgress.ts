export interface WaitCopy {
  title: string;
  detail: string;
  /** Remaining time until Cursor timeout, counting down to 00:00:00. */
  elapsedLabel: string;
  remainingMs: number;
  timedOut: boolean;
}

/** Matches backend ``CURSOR_TIMEOUT_SECONDS`` default (20 minutes). */
export const DEFAULT_CURSOR_TIMEOUT_MS = 1_200_000;

const STEPS: Array<{ afterMs: number; title: string; detail: string }> = [
  { afterMs: 0, title: 'Starting this stage', detail: 'Pulling the card, prompt, and connectors.' },
  { afterMs: 8_000, title: 'Pulling tools', detail: 'Attaching Jira, Polarion, GitHub, or Norns MCP.' },
  { afterMs: 20_000, title: 'Talking to the model', detail: 'Waiting on the first reply. This is usually quick.' },
  { afterMs: 45_000, title: 'Still pulling', detail: 'The agent is working. Cursor cloud runs often take a few minutes.' },
  { afterMs: 90_000, title: 'Waiting on tools', detail: 'Search, create, and MCP calls can sit here for a while. You can leave this card open.' },
  { afterMs: 180_000, title: 'Long wait', detail: 'Still going. No need to click Run again — extra clicks are ignored.' },
  { afterMs: 720_000, title: 'Near the time limit', detail: 'Cursor stages stop when this countdown hits 00:00:00. Hang on, or use DeepSeek/OpenAI next time.' },
  {
    afterMs: 1_200_000,
    title: 'Past the Cursor wait',
    detail: 'Norns should have stopped this Cursor wait. If the card is still running, Control Room was likely restarted — reject or run again.'
  }
];

/** Elapsed clock (tests / debugging). Prefer ``formatCountdown`` in the UI. */
export function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  }
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

/** Remaining time as HH:MM:SS, counting down to 00:00:00 at timeout. */
export function formatCountdown(remainingMs: number): string {
  const total = Math.max(0, Math.ceil(remainingMs / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

export function waitCopy(elapsedMs: number, timeoutMs: number = DEFAULT_CURSOR_TIMEOUT_MS): WaitCopy {
  const elapsed = Math.max(0, elapsedMs);
  const timeout = Math.max(1_000, timeoutMs);
  const remainingMs = Math.max(0, timeout - elapsed);
  const timedOut = remainingMs <= 0;

  let step = STEPS[0];
  for (const candidate of STEPS) {
    // Scale the canned “past wait” step to the configured timeout.
    const afterMs = candidate.afterMs >= 1_200_000 ? timeout : Math.min(candidate.afterMs, timeout);
    if (elapsed >= afterMs) {
      step = candidate;
    }
  }
  if (timedOut) {
    step = STEPS[STEPS.length - 1];
  }

  return {
    title: step.title,
    detail: step.detail,
    elapsedLabel: formatCountdown(remainingMs),
    remainingMs,
    timedOut
  };
}
