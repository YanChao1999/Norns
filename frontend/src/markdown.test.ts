import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { MarkdownPreview } from './components/MarkdownPreview';

function html(source: string, compact = false): string {
  return renderToStaticMarkup(createElement(MarkdownPreview, { source, compact }));
}

describe('MarkdownPreview', () => {
  it('renders headings, lists, emphasis, fenced code, and tables', () => {
    const markup = html(`# Title

A **bold** and *italic* note with \`code\`.

- one
- two

| col | n |
| --- | - |
| a | 1 |

\`\`\`json
{"ok": true}
\`\`\`
`);
    expect(markup).toContain('md-h1');
    expect(markup).toContain('Title');
    expect(markup).toContain('<strong>');
    expect(markup).toContain('<em>');
    expect(markup).toContain('md-inline-code');
    expect(markup).toContain('<ul');
    expect(markup).toContain('md-table');
    expect(markup).toContain('json');
    expect(markup).toContain('{&quot;ok&quot;: true}');
  });

  it('drops javascript links and keeps http(s)', () => {
    const markup = html('[safe](https://example.com) [bad](javascript:alert(1))');
    expect(markup).toContain('href="https://example.com"');
    expect(markup).not.toContain('javascript:');
  });

  it('does not italicize snake_case identifiers', () => {
    expect(html('Use NORNS_HOME and card_id here.')).toContain('Use NORNS_HOME and card_id here.');
    expect(html('Use NORNS_HOME and card_id here.')).not.toContain('<em>');
  });

  it('renders compact previews without nested anchors', () => {
    const markup = html('[safe](https://example.com)', true);
    expect(markup).toContain('md-link-text');
    expect(markup).not.toContain('<a ');
  });
});
