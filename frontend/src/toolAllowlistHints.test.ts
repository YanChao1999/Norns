import { describe, expect, it } from 'vitest';

import { isEmptyAllowlist, unavailableAllowlisted } from './toolAllowlistHints';

describe('toolAllowlistHints', () => {
  it('treats missing or empty allowlist as empty', () => {
    expect(isEmptyAllowlist([])).toBe(true);
    expect(isEmptyAllowlist(undefined)).toBe(true);
    expect(isEmptyAllowlist(['jira'])).toBe(false);
  });

  it('lists checked plugins that are not available', () => {
    const plugins = [
      { name: 'norns', available: true, requires_connector: null },
      { name: 'jira', available: false, requires_connector: 'jira' },
      { name: 'abom', available: false, requires_connector: null }
    ];
    expect(unavailableAllowlisted(['jira', 'abom', 'norns'], plugins).map((p) => p.name)).toEqual(['jira', 'abom']);
    expect(unavailableAllowlisted(['norns'], plugins)).toEqual([]);
    expect(unavailableAllowlisted([], plugins)).toEqual([]);
  });
});
