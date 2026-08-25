import { describe, expect, it } from 'vitest';

import { isPlaceholderRun, NO_API_KEY_HINT, PLACEHOLDER_RUN_HINT } from './runHints';

describe('run hints', () => {
  it('detects a practice run from the placeholder flag', () => {
    expect(isPlaceholderRun({ model_output: 'ok', handoff: { placeholder: true } })).toBe(true);
    expect(isPlaceholderRun({ model_output: 'Looks good', handoff: { summary: 'Looks good' } })).toBe(false);
  });

  it('still recognizes older placeholder copy without the flag', () => {
    expect(
      isPlaceholderRun({
        model_output: "OpenAI API key not configured. Placeholder run created for stage 'Urd'.",
        handoff: {}
      })
    ).toBe(true);
  });

  it('tells people how to make a real run', () => {
    expect(NO_API_KEY_HINT).toMatch(/Cursor|DeepSeek|OpenAI/i);
    expect(PLACEHOLDER_RUN_HINT).toMatch(/practice run/i);
  });
});
