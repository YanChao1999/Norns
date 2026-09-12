import { describe, expect, it } from 'vitest';

import { DEFAULT_CURSOR_TIMEOUT_MS, formatCountdown, formatElapsed, waitCopy } from './waitProgress';

describe('waitProgress', () => {
  it('formats elapsed as m:ss', () => {
    expect(formatElapsed(0)).toBe('0:00');
    expect(formatElapsed(12_000)).toBe('0:12');
    expect(formatElapsed(75_000)).toBe('1:15');
    expect(formatElapsed(28_810_000)).toBe('8:00:10');
  });

  it('counts down remaining time to 00:00:00', () => {
    expect(formatCountdown(DEFAULT_CURSOR_TIMEOUT_MS)).toBe('00:20:00');
    expect(formatCountdown(1_000)).toBe('00:00:01');
    expect(formatCountdown(0)).toBe('00:00:00');
    expect(formatCountdown(-5_000)).toBe('00:00:00');
  });

  it('starts with a pull message and shows remaining timeout', () => {
    expect(waitCopy(0).title).toMatch(/starting/i);
    expect(waitCopy(0).elapsedLabel).toBe('00:20:00');
    expect(waitCopy(10_000).title).toMatch(/pulling tools/i);
    expect(waitCopy(10_000).elapsedLabel).toBe('00:19:50');
    expect(waitCopy(50_000).detail).toMatch(/cursor/i);
    expect(waitCopy(200_000).detail).toMatch(/run again/i);
    expect(waitCopy(800_000).detail).toMatch(/00:00:00/i);
    expect(waitCopy(1_300_000).title).toMatch(/past the cursor wait/i);
    expect(waitCopy(1_300_000).elapsedLabel).toBe('00:00:00');
    expect(waitCopy(1_300_000).timedOut).toBe(true);
  });

  it('scales the past-wait step to a custom timeout', () => {
    const short = waitCopy(61_000, 60_000);
    expect(short.timedOut).toBe(true);
    expect(short.elapsedLabel).toBe('00:00:00');
    expect(short.title).toMatch(/past the cursor wait/i);
  });
});
