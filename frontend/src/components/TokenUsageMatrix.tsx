import { useQuery } from '@tanstack/react-query';

import { apiClient } from '../api/client';
import { useI18n } from '../i18n';

export interface StageUsageRow {
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

export interface CardUsageMatrix {
  card_id: string;
  board_id: string;
  totals: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    rounds: number;
    source: string;
  };
  by_stage: StageUsageRow[];
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

export function TokenUsageMatrix({ cardId }: { cardId: string }) {
  const { t } = useI18n();
  const { data, isLoading, isError } = useQuery({
    queryKey: ['usage', cardId],
    queryFn: () => apiClient.get<CardUsageMatrix>(`/cards/${cardId}/usage`),
    refetchInterval: 4000
  });

  if (isLoading) {
    return <p className="muted">{t('detail.usageLoading')}</p>;
  }
  if (isError || !data) {
    return null;
  }

  const rows = data.by_stage.filter((row) => row.run_count > 0 || row.total_tokens > 0);
  if (!rows.length && data.totals.total_tokens === 0) {
    return (
      <section className="token-usage">
        <h3>{t('detail.usageTitle')}</h3>
        <p className="muted">{t('detail.usageEmpty')}</p>
      </section>
    );
  }

  return (
    <section className="token-usage">
      <h3>{t('detail.usageTitle')}</h3>
      <p className="muted">{t('detail.usageHint')}</p>
      <div className="token-usage-table-wrap">
        <table className="token-usage-table">
          <thead>
            <tr>
              <th>{t('detail.usageStage')}</th>
              <th>{t('detail.usageModel')}</th>
              <th>{t('detail.usagePrompt')}</th>
              <th>{t('detail.usageCompletion')}</th>
              <th>{t('detail.usageTotal')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.stage_id}>
                <td>{row.stage_name}</td>
                <td className="muted">
                  {row.model || '—'}
                  {row.provider ? ` · ${row.provider}` : ''}
                  {row.source === 'unavailable' ? ` (${t('detail.usageUnknown')})` : ''}
                  {row.source === 'practice' ? ` (${t('detail.usagePractice')})` : ''}
                </td>
                <td>{formatTokens(row.prompt_tokens)}</td>
                <td>{formatTokens(row.completion_tokens)}</td>
                <td>
                  <strong>{formatTokens(row.total_tokens)}</strong>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={2}>
                <strong>{t('detail.usageCardTotal')}</strong>
              </td>
              <td>
                <strong>{formatTokens(data.totals.prompt_tokens)}</strong>
              </td>
              <td>
                <strong>{formatTokens(data.totals.completion_tokens)}</strong>
              </td>
              <td>
                <strong>{formatTokens(data.totals.total_tokens)}</strong>
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </section>
  );
}
