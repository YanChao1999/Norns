import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FormEvent, useState } from 'react';

import { apiClient } from '../api/client';
import { useI18n } from '../i18n';

export interface BakeoffArmReport {
  label: string;
  card_id: string;
  stage_id: string;
  stage_name: string;
  status: string;
  model: string;
  llm_provider: string;
  temperature: number | null;
  tool_allowlist: string[];
  system_prompt: string;
  summary: string;
  output: string;
  recommendation: 'approve' | 'reject' | null;
  usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    rounds: number;
    source: string;
    provider: string;
    model: string;
  };
}

export interface BakeoffCompare {
  bakeoff_id: string | null;
  root_card_id: string;
  board_id: string;
  status: string;
  prompt: string;
  arms: BakeoffArmReport[];
  totals: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    rounds: number;
    source: string;
  };
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

function toolsLabel(tools: string[]): string {
  return tools.length ? tools.join(' · ') : '—';
}

export function BakeoffComparePanel({ cardId, idle }: { cardId: string; idle: boolean }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [labelA, setLabelA] = useState('A');
  const [labelB, setLabelB] = useState('B');
  const [toolsA, setToolsA] = useState('norns,sandbox');
  const [toolsB, setToolsB] = useState('');
  const [prompt, setPrompt] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['bakeoff', cardId],
    queryFn: () => apiClient.get<BakeoffCompare>(`/cards/${cardId}/bakeoff`),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'running' || status === 'waiting' ? 3000 : false;
    }
  });

  const startMutation = useMutation({
    mutationFn: async () => {
      const parseTools = (raw: string) =>
        raw
          .split(/[,;\s]+/)
          .map((item) => item.trim())
          .filter(Boolean);
      return apiClient.post<BakeoffCompare>(`/cards/${cardId}/bakeoff`, {
        prompt: prompt.trim() || null,
        arms: [
          { label: labelA.trim() || 'A', tool_allowlist: parseTools(toolsA), temperature: 0.2 },
          { label: labelB.trim() || 'B', tool_allowlist: parseTools(toolsB), temperature: 0.2 }
        ],
        require_approval: false,
        auto_start: true
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['bakeoff', cardId] });
      void queryClient.invalidateQueries({ queryKey: ['board'] });
      void queryClient.invalidateQueries({ queryKey: ['runs', cardId] });
      void queryClient.invalidateQueries({ queryKey: ['usage', cardId] });
      setOpen(false);
    }
  });

  const hasBakeoff = Boolean(data?.bakeoff_id && data.arms.length);

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!idle || startMutation.isPending) {
      return;
    }
    startMutation.mutate();
  }

  return (
    <section className="bakeoff-compare">
      <div className="bakeoff-compare-head">
        <h3>{t('detail.bakeoffTitle')}</h3>
        {idle ? (
          <button type="button" className="btn btn-ghost btn-compact" onClick={() => setOpen((value) => !value)}>
            {open ? t('detail.bakeoffCancel') : t('detail.bakeoffStart')}
          </button>
        ) : null}
      </div>
      <p className="muted">{t('detail.bakeoffHint')}</p>

      {open ? (
        <form className="bakeoff-form" onSubmit={onSubmit}>
          <label>
            <span>{t('detail.bakeoffPrompt')}</span>
            <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={3} placeholder={t('detail.bakeoffPromptPlaceholder')} />
          </label>
          <div className="bakeoff-arms">
            <label>
              <span>{t('detail.bakeoffArmLabel')} A</span>
              <input value={labelA} onChange={(event) => setLabelA(event.target.value)} />
            </label>
            <label>
              <span>{t('detail.bakeoffTools')} A</span>
              <input value={toolsA} onChange={(event) => setToolsA(event.target.value)} placeholder="norns,sandbox" />
            </label>
            <label>
              <span>{t('detail.bakeoffArmLabel')} B</span>
              <input value={labelB} onChange={(event) => setLabelB(event.target.value)} />
            </label>
            <label>
              <span>{t('detail.bakeoffTools')} B</span>
              <input value={toolsB} onChange={(event) => setToolsB(event.target.value)} placeholder={t('detail.bakeoffToolsEmpty')} />
            </label>
          </div>
          <button type="submit" disabled={startMutation.isPending || !idle}>
            {startMutation.isPending ? t('detail.bakeoffStarting') : t('detail.bakeoffRun')}
          </button>
          {startMutation.isError ? <p className="error">{t('detail.bakeoffError')}</p> : null}
        </form>
      ) : null}

      {isLoading && !data ? <p className="muted">{t('detail.bakeoffLoading')}</p> : null}

      {hasBakeoff && data ? (
        <>
          <p className="bakeoff-status">
            {t('detail.bakeoffStatus', { status: data.status })}
            {data.prompt ? ` · ${data.prompt.slice(0, 80)}${data.prompt.length > 80 ? '…' : ''}` : ''}
          </p>
          <div className="bakeoff-table-wrap">
            <table className="bakeoff-table">
              <thead>
                <tr>
                  <th>{t('detail.bakeoffArm')}</th>
                  <th>{t('detail.bakeoffTools')}</th>
                  <th>{t('detail.usageModel')}</th>
                  <th>{t('detail.usageTotal')}</th>
                  <th>{t('detail.bakeoffOutcome')}</th>
                </tr>
              </thead>
              <tbody>
                {data.arms.map((arm) => (
                  <tr key={arm.label}>
                    <td>
                      <strong>{arm.label}</strong>
                      <div className="muted">{arm.status}</div>
                    </td>
                    <td>{toolsLabel(arm.tool_allowlist)}</td>
                    <td className="muted">
                      {arm.model || arm.usage.model || '—'}
                      {arm.llm_provider || arm.usage.provider ? ` · ${arm.llm_provider || arm.usage.provider}` : ''}
                    </td>
                    <td>
                      <strong>{formatTokens(arm.usage.total_tokens)}</strong>
                      <div className="muted">
                        {formatTokens(arm.usage.prompt_tokens)} / {formatTokens(arm.usage.completion_tokens)}
                      </div>
                    </td>
                    <td>
                      {arm.recommendation ? (
                        <span className={`bakeoff-rec bakeoff-rec-${arm.recommendation}`}>{arm.recommendation}</span>
                      ) : (
                        <span className="muted">—</span>
                      )}
                      {arm.summary ? <div className="bakeoff-summary">{arm.summary}</div> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan={3}>
                    <strong>{t('detail.bakeoffFamilyTotal')}</strong>
                  </td>
                  <td>
                    <strong>{formatTokens(data.totals.total_tokens)}</strong>
                  </td>
                  <td />
                </tr>
              </tfoot>
            </table>
          </div>
        </>
      ) : null}
    </section>
  );
}
