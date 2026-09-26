import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { apiClient } from '../api/client';
import { useI18n } from '../i18n';

interface UsageTotals {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  rounds: number;
  source: string;
}

interface StageUsageSummary {
  stage_id: string;
  stage_name: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  rounds: number;
  source: string;
  provider: string;
  model: string;
  run_count: number;
}

interface CardUsageSummary {
  card_id: string;
  title: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  rounds: number;
  source: string;
  run_count: number;
}

export interface BoardUsageMatrix {
  board_id: string;
  totals: UsageTotals;
  card_count: number;
  run_count: number;
  by_stage: StageUsageSummary[];
  by_card: CardUsageSummary[];
}

function formatTokens(value: number): string {
  if (!value) {
    return '0';
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(value >= 10000 ? 0 : 1)}k`;
  }
  return String(value);
}

function promptShare(prompt: number, total: number): string {
  if (!total) {
    return '—';
  }
  return `${Math.round((prompt / total) * 100)}%`;
}

export function TokenUsageDashboard({ boardId }: { boardId: string }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const { data, isLoading, isError } = useQuery({
    queryKey: ['board-usage', boardId],
    queryFn: () => apiClient.get<BoardUsageMatrix>(`/boards/${boardId}/usage`),
    refetchInterval: 8000
  });

  if (isLoading) {
    return (
      <div className="board-usage-summary is-loading" aria-busy="true">
        <span className="muted">{t('board.usageLoading')}</span>
      </div>
    );
  }
  if (isError || !data) {
    return null;
  }

  const empty = data.totals.total_tokens === 0 && data.card_count === 0;
  const stageRows = data.by_stage.filter((row) => row.run_count > 0 || row.total_tokens > 0);
  const cardRows = data.by_card.slice(0, 8);

  return (
    <div className={`board-usage-summary${open ? ' is-open' : ''}`}>
      <button type="button" className="board-usage-toggle" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
        <span className="board-usage-label">{t('board.usageTitle')}</span>
        {empty ? (
          <span className="muted">{t('board.usageEmpty')}</span>
        ) : (
          <span className="board-usage-figures">
            <strong>{formatTokens(data.totals.total_tokens)}</strong>
            <span className="muted">
              {t('board.usageSplit', {
                prompt: formatTokens(data.totals.prompt_tokens),
                completion: formatTokens(data.totals.completion_tokens),
                share: promptShare(data.totals.prompt_tokens, data.totals.total_tokens)
              })}
            </span>
            <span className="muted">
              · {t('board.usageCards', { count: data.card_count })}
              {data.totals.rounds ? ` · ${t('board.usageRounds', { count: data.totals.rounds })}` : ''}
            </span>
          </span>
        )}
        <span className="board-usage-chevron" aria-hidden="true">
          {open ? '▾' : '▸'}
        </span>
      </button>

      {open ? (
        <div className="board-usage-panel">
          {empty ? (
            <p className="muted">{t('board.usageEmptyHint')}</p>
          ) : (
            <>
              <p className="muted board-usage-hint">{t('board.usageHint')}</p>
              {stageRows.length ? (
                <div className="board-usage-table-wrap">
                  <table className="board-usage-table">
                    <thead>
                      <tr>
                        <th>{t('detail.usageStage')}</th>
                        <th>{t('detail.usageModel')}</th>
                        <th>{t('detail.usageRounds')}</th>
                        <th>{t('detail.usagePrompt')}</th>
                        <th>{t('detail.usageCompletion')}</th>
                        <th>{t('detail.usagePromptShare')}</th>
                        <th>{t('detail.usageTotal')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {stageRows.map((row) => (
                        <tr key={row.stage_id}>
                          <td>
                            {row.stage_name}
                            {row.run_count > 1 ? <div className="muted">{t('detail.usageRunCount', { count: row.run_count })}</div> : null}
                          </td>
                          <td className="muted">
                            {row.model || '—'}
                            {row.provider ? ` · ${row.provider}` : ''}
                          </td>
                          <td>{row.rounds || '—'}</td>
                          <td>{formatTokens(row.prompt_tokens)}</td>
                          <td>{formatTokens(row.completion_tokens)}</td>
                          <td className="muted">{promptShare(row.prompt_tokens, row.total_tokens)}</td>
                          <td>
                            <strong>{formatTokens(row.total_tokens)}</strong>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
              {cardRows.length ? (
                <div className="board-usage-cards">
                  <h4>{t('board.usageByCard')}</h4>
                  <ul>
                    {cardRows.map((row) => (
                      <li key={row.card_id}>
                        <span className="board-usage-card-title">{row.title}</span>
                        <span className="muted">
                          {formatTokens(row.total_tokens)} · {promptShare(row.prompt_tokens, row.total_tokens)} prompt
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}
