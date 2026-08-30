import { describe, expect, it } from 'vitest';

import { cardFaceSummary } from './cardPreview';

describe('cardFaceSummary', () => {
  it('prefers the structured LLM recommendation over handoff markdown', () => {
    expect(
      cardFaceSummary(
        `## Urd handoff

| Action | Result |
|---|---|
| Polarion search | Failed |
`,
        { recommendation: 'reject', reason: 'Polarion client is broken and no create-workitem tool exists.' }
      )
    ).toBe('Reject — Polarion client is broken and no create-workitem tool exists.');
  });

  it('prefers an LLM recommendation line', () => {
    expect(
      cardFaceSummary(`## Urd handoff

DECISION: reject
REASON: Polarion client is broken and no create-workitem tool exists.

| Action | Result |
|---|---|
| Polarion search | Failed |
`)
    ).toBe('Reject — Polarion client is broken and no create-workitem tool exists.');
  });

  it('keeps an Approve/Reject em-dash line', () => {
    expect(cardFaceSummary('Reject — Polarion client is broken (tracking only via NOR-8).')).toBe(
      'Reject — Polarion client is broken (tracking only via NOR-8).'
    );
  });

  it('skips headings and tables and uses the first prose line', () => {
    expect(
      cardFaceSummary(`## Urd handoff

### Request
Create **one** software requirement in Polarion for Norns.

| Action | Result |
|---|---|
| Polarion search | Failed |
`)
    ).toBe('Create one software requirement in Polarion for Norns.');
  });

  it('returns empty for blank bodies', () => {
    expect(cardFaceSummary('   ')).toBe('');
  });
});
