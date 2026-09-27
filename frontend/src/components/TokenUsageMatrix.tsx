import { Fragment, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { apiClient } from '../api/client';
import { useI18n } from '../i18n';

export interface InputBreakdown {
  method?: string;
  kind?: string;
  system: number;
  task: number;
  tool_schemas: number;
  assistant: number;
  tool_results: number;
  skills: number;
  estimated_prompt: number;
}

export interface RunUsageRow {
  run_id: string;
  status: string;
  created_at: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  rounds: number;
  source: string;
  provider: string;
  model: string;
  input_breakdown?: InputBreakdown;
}

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
  runs?: RunUsageRow[];
  input_breakdown?: InputBreakdown;
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
    input_breakdown?: InputBreakdown;
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

function promptShare(prompt: number, total: number): string {
  if (!total) {
    return '—';
  }
  return `${Math.round((prompt / total) * 100)}%`;
}

function sourceNote(source: string): string {
  if (source === 'unavailable') {
    return ' (not reported)';
  }
  if (source === 'practice') {
    return ' (practice)';
  }
  if (source === 'cursor') {
    return ' (cursor sdk)';
  }
  return '';
}

const BREAKDOWN_ROWS: Array<{
  key: keyof InputBreakdown;
  label:
    | 'detail.usageInputSystem'
    | 'detail.usageInputTask'
    | 'detail.usageInputToolSchemas'
    | 'detail.usageInputAssistant'
    | 'detail.usageInputToolResults'
    | 'detail.usageInputSkills';
}> = [
  { key: 'system', label: 'detail.usageInputSystem' },
  { key: 'task', label: 'detail.usageInputTask' },
  { key: 'tool_schemas', label: 'detail.usageInputToolSchemas' },
  { key: 'assistant', label: 'detail.usageInputAssistant' },
  { key: 'tool_results', label: 'detail.usageInputToolResults' },
  { key: 'skills', label: 'detail.usageInputSkills' }
];

function InputBreakdownPanel({ breakdown }: { breakdown: InputBreakdown }) {
  const { t } = useI18n();
  const estimated = breakdown.estimated_prompt || 0;
  if (!estimated) {
    return null;
  }
  return (
    <div className="token-usage-input">
      <h4>{t('detail.usageInputTitle')}</h4>
      <p className="muted">{t('detail.usageInputHint')}</p>
      <ul className="token-usage-input-list">
        {BREAKDOWN_ROWS.map((row) => {
          const value = Number(breakdown[row.key] || 0);
          return (
            <li key={row.key}>
              <span>{t(row.label)}</span>
              <span className="token-usage-input-value">
                {formatTokens(value)}
                <span className="muted"> · {promptShare(value, estimated)}</span>
              </span>
            </li>
          );
        })}
        <li className="token-usage-input-total">
          <span>{t('detail.usageInputEstimated')}</span>
          <strong>{formatTokens(estimated)}</strong>
        </li>
      </ul>
    </div>
  );
}

export function TokenUsageMatrix({ cardId, active = false }: { cardId: string; active?: boolean }) {
  const { t } = useI18n();
  const [openStageId, setOpenStageId] = useState<string | null>(null);
  const { data, isLoading, isError } = useQuery({
    queryKey: ['usage', cardId],
    queryFn: () => apiClient.get<CardUsageMatrix>(`/cards/${cardId}/usage`),
    refetchInterval: active ? 4000 : false
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
      <p className="muted token-usage-prompt-note">{t('detail.usagePromptNote')}</p>
      <div className="token-usage-table-wrap">
        <table className="token-usage-table">
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
            {rows.map((row) => {
              const open = openStageId === row.stage_id;
              const runRows = row.runs ?? [];
              return (
                <Fragment key={row.stage_id}>
                  <tr>
                    <td>
                      {runRows.length > 1 ? (
                        <button type="button" className="btn btn-ghost btn-compact" onClick={() => setOpenStageId(open ? null : row.stage_id)}>
                          {open ? '▾' : '▸'} {row.stage_name}
                        </button>
                      ) : (
                        row.stage_name
                      )}
                      {row.run_count > 1 ? <div className="muted">{t('detail.usageRunCount', { count: row.run_count })}</div> : null}
                    </td>
                    <td className="muted">
                      {row.model || '—'}
                      {row.provider ? ` · ${row.provider}` : ''}
                      {sourceNote(row.source)}
                    </td>
                    <td>{row.rounds || '—'}</td>
                    <td>{formatTokens(row.prompt_tokens)}</td>
                    <td>{formatTokens(row.completion_tokens)}</td>
                    <td className="muted">{promptShare(row.prompt_tokens, row.total_tokens)}</td>
                    <td>
                      <strong>{formatTokens(row.total_tokens)}</strong>
                    </td>
                  </tr>
                  {open
                    ? runRows.map((run, index) => (
                        <tr key={run.run_id} className="token-usage-run-row">
                          <td className="muted">
                            {t('detail.usageRunLabel', { index: index + 1 })}
                            {run.created_at ? <div className="muted">{run.created_at.replace('T', ' ').slice(0, 19)} UTC</div> : null}
                          </td>
                          <td className="muted">
                            {run.model || row.model || '—'}
                            {sourceNote(run.source)}
                          </td>
                          <td>{run.rounds || '—'}</td>
                          <td>{formatTokens(run.prompt_tokens)}</td>
                          <td>{formatTokens(run.completion_tokens)}</td>
                          <td className="muted">{promptShare(run.prompt_tokens, run.total_tokens)}</td>
                          <td>{formatTokens(run.total_tokens)}</td>
                        </tr>
                      ))
                    : null}
                </Fragment>
              );
            })}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={3}>
                <strong>{t('detail.usageCardTotal')}</strong>
                {data.totals.rounds ? <span className="muted"> · {t('detail.usageRoundsTotal', { count: data.totals.rounds })}</span> : null}
              </td>
              <td>
                <strong>{formatTokens(data.totals.prompt_tokens)}</strong>
              </td>
              <td>
                <strong>{formatTokens(data.totals.completion_tokens)}</strong>
              </td>
              <td className="muted">{promptShare(data.totals.prompt_tokens, data.totals.total_tokens)}</td>
              <td>
                <strong>{formatTokens(data.totals.total_tokens)}</strong>
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
      {data.totals.input_breakdown ? <InputBreakdownPanel breakdown={data.totals.input_breakdown} /> : null}
    </section>
  );
}
