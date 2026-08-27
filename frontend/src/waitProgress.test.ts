import { describe, expect, it } from 'vitest';

import { formatElapsed, waitCopy } from './waitProgress';

describe('waitProgress', () => {
  it('formats elapsed as m:ss', () => {
    expect(formatElapsed(0)).toBe('0:00');
    expect(formatElapsed(12_000)).toBe('0:12');
    expect(formatElapsed(75_000)).toBe('1:15');
  });

  it('starts with a pull message and grows more patient', () => {
    expect(waitCopy(0).title).toMatch(/starting/i);
    expect(waitCopy(10_000).title).toMatch(/pulling tools/i);
    expect(waitCopy(50_000).detail).toMatch(/cursor/i);
    expect(waitCopy(200_000).detail).toMatch(/run again/i);
  });
});
