/** Short board-card blurb: LLM-style recommend, not the full handoff markdown. */

const MAX_LENGTH = 180;

export function formatRecommendation(recommendation?: string | null, reason?: string | null): string {
  const verb = (recommendation || '').trim().toLowerCase();
  if (verb !== 'approve' && verb !== 'reject') {
    return '';
  }
  const label = verb === 'approve' ? 'Approve' : 'Reject';
  const why = (reason || '').replace(/\s+/g, ' ').trim();
  return why ? `${label} — ${why}` : label;
}

export function cardFaceSummary(
  body: string,
  rec?: { recommendation?: string | null; reason?: string | null },
  maxLength = MAX_LENGTH
): string {
  const fromRec = formatRecommendation(rec?.recommendation, rec?.reason);
  if (fromRec) {
    return clip(fromRec, maxLength);
  }
  const source = body.replace(/\r\n/g, '\n').trim();
  if (!source) {
    return '';
  }
  const fromDecision = recommendationBlurb(source);
  if (fromDecision) {
    return clip(fromDecision, maxLength);
  }
  return clip(firstProse(source), maxLength);
}

function recommendationBlurb(source: string): string {
  const decision = /(?:^|\n)\s*(?:\*{0,2})(?:DECISION|Recommendation)(?:\*{0,2})\s*:\s*(approve|reject)\b/i.exec(source);
  const reason = /(?:^|\n)\s*(?:\*{0,2})REASON(?:\*{0,2})\s*:\s*(.+)/i.exec(source);
  if (decision) {
    const verb = titleCase(decision[1]);
    const why = cleanLine(reason?.[1] ?? '');
    return why ? `${verb} — ${why}` : verb;
  }
  const inline = /(?:^|\n)\s*\*{0,2}(Approve|Reject)\*{0,2}\s*[—–-]\s+(.+)/i.exec(source);
  if (inline) {
    return `${titleCase(inline[1])} — ${cleanLine(inline[2])}`;
  }
  return '';
}

function firstProse(source: string): string {
  const chunks: string[] = [];
  for (const line of source.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) {
      if (chunks.length) {
        break;
      }
      continue;
    }
    if (isSkippableLine(trimmed)) {
      continue;
    }
    if (trimmed.startsWith('```')) {
      break;
    }
    chunks.push(stripInlineMarkdown(trimmed));
    if (chunks.join(' ').length >= 80) {
      break;
    }
  }
  return chunks.join(' ').replace(/\s+/g, ' ').trim();
}

function isSkippableLine(line: string): boolean {
  return (
    /^#{1,6}\s/.test(line) ||
    /^[-*+]\s/.test(line) ||
    /^\d+[.)]\s/.test(line) ||
    /^\|.+\|/.test(line) ||
    /^:?-+:?(\s*\|\s*:?-+:?)+$/.test(line) ||
    /^(---|\*\*\*|___)$/.test(line) ||
    /^>\s?/.test(line)
  );
}

function stripInlineMarkdown(line: string): string {
  return line
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/\*(.+?)\*/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .trim();
}

function cleanLine(value: string): string {
  return stripInlineMarkdown(value).replace(/\s+/g, ' ').trim();
}

function titleCase(value: string): string {
  const lower = value.trim().toLowerCase();
  return lower ? lower[0].toUpperCase() + lower.slice(1) : '';
}

function clip(value: string, maxLength: number): string {
  if (value.length <= maxLength) {
    return value;
  }
  const sliced = value.slice(0, maxLength - 1);
  const cut = sliced.lastIndexOf(' ');
  return `${(cut > 40 ? sliced.slice(0, cut) : sliced).trim()}…`;
}
