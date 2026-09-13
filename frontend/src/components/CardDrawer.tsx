import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '../api/client';
import {
  buildJourney,
  buildStagePath,
  compareRunDecision,
  formatRunTime,
  handoffSummary,
  journeyStateLabel,
  latestFinalizedForStage,
  llmLabel,
  pluginsSnapshot,
  runsForStage,
  safeHttpUrl,
  sandboxLabel,
  stageName,
  StagePathNode
} from '../cardJourney';
import { Handoff, approveLabel, rejectLabel } from '../gateLabels';
import { useI18n } from '../i18n';
import { PLACEHOLDER_RUN_HINT, isPlaceholderRun } from '../runHints';
import { STATUS_LABEL } from '../status';
import { AgentRun, BoardDetail, Card } from '../types';
import { appendOperatorQuestion } from '../writeGate';
import { Dialog } from './Dialog';
import { MarkdownPreview } from './MarkdownPreview';
import { WaitLive } from './WaitLive';

interface Props {
  card: Card | null;
  board?: BoardDetail;
  practiceMode?: boolean;
  onClose: () => void;
  onOpenHistory?: () => void;
}

function agentRecommendation(value: unknown): 'approve' | 'reject' | null {
  return value === 'approve' || value === 'reject' ? value : null;
}

export function CardDrawer({ card, board, practiceMode = false, onClose, onOpenHistory }: Props) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const previousStatus = useRef<{ id?: string; status?: string }>({});
  const [runStarted, setRunStarted] = useState(false);
  const [askOpen, setAskOpen] = useState(false);
  const [askText, setAskText] = useState('');
  const [askNotice, setAskNotice] = useState('');
  const [expandedStageId, setExpandedStageId] = useState<string | null>(null);

  const { data: runs = [] } = useQuery({
    enabled: Boolean(card),
    queryKey: ['runs', card?.id],
    queryFn: () => apiClient.get<AgentRun[]>(`/cards/${card?.id}/runs`),
    refetchInterval: card?.status === 'running' || card?.status === 'waiting_tool_approval' ? 2000 : false
  });

  useEffect(() => {
    setRunStarted(false);
    setAskOpen(false);
    setAskText('');
    setAskNotice('');
    setExpandedStageId(null);
  }, [card?.id]);

  useEffect(() => {
    setRunStarted(false);
  }, [card?.status]);

  useEffect(() => {
    const sameCard = previousStatus.current.id === card?.id;
    if (sameCard && previousStatus.current.status === 'running' && card?.status && card.status !== 'running') {
      void queryClient.invalidateQueries({ queryKey: ['runs', card.id] });
    }
    previousStatus.current = { id: card?.id, status: card?.status };
  }, [card?.id, card?.status, queryClient]);

  const approvalMutation = useMutation({
    mutationFn: async (approved: boolean) => {
      const currentHandoff = (latestFinalizedForStage(runs, card?.current_stage_id ?? '')?.handoff ?? {}) as Handoff;
      return apiClient.post(`/cards/${card?.id}/approve`, {
        approved,
        comment: gateComment(approved, agentRecommendation(currentHandoff.recommendation))
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['board', card?.board_id] });
      queryClient.invalidateQueries({ queryKey: ['runs', card?.id] });
    }
  });

  const writeMutation = useMutation({
    mutationFn: async (approved: boolean) =>
      apiClient.post(`/cards/${card?.id}/approve-writes`, {
        approved,
        comment: approved ? 'Confirmed pending writes' : 'Declined pending writes'
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['board', card?.board_id] });
      queryClient.invalidateQueries({ queryKey: ['runs', card?.id] });
    }
  });

  const runMutation = useMutation({
    mutationFn: async () => apiClient.post(`/cards/${card?.id}/run`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['board', card?.board_id] });
      queryClient.invalidateQueries({ queryKey: ['runs', card?.id] });
    },
    onError: () => {
      queryClient.invalidateQueries({ queryKey: ['board', card?.board_id] });
      queryClient.invalidateQueries({ queryKey: ['runs', card?.id] });
      setRunStarted(false);
    }
  });

  const askMutation = useMutation({
    mutationFn: async (question: string) => {
      if (!card) {
        throw new Error('No card');
      }
      const nextBody = appendOperatorQuestion(card.body, question);
      await apiClient.put(`/cards/${card.id}`, { body: nextBody });
      const canStart = card.status === 'idle' || card.status === 'blocked';
      if (canStart) {
        setRunStarted(true);
        await apiClient.post(`/cards/${card.id}/run`);
        return 'ran' as const;
      }
      return 'saved' as const;
    },
    onSuccess: (result) => {
      setAskText('');
      setAskOpen(false);
      setAskNotice(result === 'ran' ? t('detail.askAgentRunning') : t('detail.askAgentSaved'));
      queryClient.invalidateQueries({ queryKey: ['board', card?.board_id] });
      queryClient.invalidateQueries({ queryKey: ['runs', card?.id] });
    },
    onError: () => {
      setRunStarted(false);
    }
  });

  const journey = useMemo(() => (card ? buildJourney(card, board, runs) : []), [board, card, runs]);
  const stagePath = useMemo(() => (card ? buildStagePath(card, board, runs) : []), [board, card, runs]);

  if (!card) {
    return null;
  }

  const currentStageId = card.current_stage_id ?? '';
  const currentStageRuns = runsForStage(runs, currentStageId);
  const latestCurrentRun = currentStageRuns.length ? currentStageRuns[currentStageRuns.length - 1] : undefined;
  const previousCurrentRun = currentStageRuns.length > 1 ? currentStageRuns[currentStageRuns.length - 2] : null;
  const inProgress = card.status === 'running' || runStarted;
  const canRun = (card.status === 'idle' || card.status === 'blocked') && !runStarted;
  const waiting = card.status === 'waiting_approval';
  const waitingWrites = card.status === 'waiting_tool_approval';
  const joining = card.status === 'waiting_join';
  const handoffRun = waitingWrites ? (latestCurrentRun ?? latestFinalizedForStage(runs, currentStageId)) : latestFinalizedForStage(runs, currentStageId);
  const handoff = (handoffRun?.handoff ?? {}) as Handoff;
  const pendingWrites = pendingWriteCalls(latestCurrentRun);
  const placeholderRun = isPlaceholderRun(handoffRun ?? latestCurrentRun);
  const summary = handoffSummary(handoffRun);
  const links = Array.isArray(handoff.links) ? handoff.links.map(String) : [];
  const recommendation = agentRecommendation(handoff.recommendation);
  const recommendationReason =
    typeof handoff.recommendation_reason === 'string'
      ? handoff.recommendation_reason.trim()
      : typeof card.recommendation_reason === 'string'
        ? card.recommendation_reason.trim()
        : '';
  const reasonCompare = latestCurrentRun ? compareRunDecision(latestCurrentRun, previousCurrentRun) : 'first';
  const plugins = pluginsSnapshot(latestCurrentRun);
  const llm = llmLabel(latestCurrentRun);
  const sandbox = sandboxLabel(latestCurrentRun);
  const outgoing = (board?.transitions ?? []).filter((edge) => edge.from_stage_id === card.current_stage_id);
  const approveLines = outgoing.filter((edge) => edge.event === 'approve');
  const rejectLines = outgoing.filter((edge) => edge.event === 'reject');
  const currentStageLabel = stageName(board, currentStageId);
  const cardCode = card.external_id?.trim() || shortId(card.id);
  const enteredAt = latestCurrentRun?.created_at ?? card.updated_at ?? card.created_at;
  const updatedAt = card.updated_at ?? latestCurrentRun?.completed_at ?? latestCurrentRun?.created_at;
  const machineName = board?.name ?? 'Delivery';
  const statusLine = detailStatus(card.status, t);

  return (
    <Dialog open onClose={onClose} labelledBy="card-drawer-title" variant="sheet">
      <article className="machine-card">
        <header className="machine-card-top">
          <div className="machine-card-brand">
            <span className="machine-card-mark" aria-hidden="true">
              ⌘
            </span>
            <div>
              <p className="machine-card-brand-name">{t('detail.brand')}</p>
              <p className="machine-card-brand-kicker">{t('detail.kicker')}</p>
            </div>
          </div>
          <div className="machine-card-title-block">
            <h2 id="card-drawer-title">
              {cardCode} {card.title}
            </h2>
            <p className="machine-card-status">{t('detail.status', { status: statusLine })}</p>
          </div>
          <div className="machine-card-meta">
            <span>{cardCode}</span>
            {updatedAt ? <span>{t('detail.updated', { time: formatRunTime(updatedAt) })}</span> : null}
            <button type="button" className="btn btn-ghost btn-compact" onClick={onClose}>
              {t('detail.close')}
            </button>
          </div>
        </header>

        <section className="machine-card-path" aria-label={t('detail.stagePath')}>
          <div className="machine-card-path-head">
            <h3>{t('detail.stagePath')}</h3>
            {stagePath.some((node) => node.parallel) ? <span className="machine-card-path-legend">{t('detail.parallelPhase')}</span> : null}
          </div>
          <ol className="stage-path">
            {stagePath.map((node, index) => (
              <li
                key={node.id}
                className={`stage-path-node is-${node.state}${node.parallel ? ' is-parallel' : ''}${node.kind !== 'stage' ? ` is-${node.kind}` : ''}`}
              >
                {index > 0 ? <span className="stage-path-connector" aria-hidden="true" /> : null}
                <button
                  type="button"
                  className="stage-path-btn"
                  disabled={node.kind !== 'stage'}
                  aria-pressed={node.kind === 'stage' && expandedStageId === node.id}
                  onClick={() => {
                    if (node.kind === 'stage') {
                      setExpandedStageId((current) => (current === node.id ? null : node.id));
                    }
                  }}
                  title={pathNodeTitle(node, t)}
                >
                  <span className="stage-path-dot" aria-hidden="true">
                    {pathGlyph(node)}
                  </span>
                  <span className="stage-path-label">
                    {node.label}
                    {node.parallel ? <em> {t('detail.inParallel')}</em> : null}
                  </span>
                  <span className="stage-path-state">{pathStateLabel(node, t)}</span>
                </button>
              </li>
            ))}
          </ol>
          {stagePath.some((node) => node.parallel) ? (
            <div className="stage-path-bracket" aria-hidden="true">
              <span>{t('detail.parallelPhase')}</span>
            </div>
          ) : null}
        </section>

        <div className="machine-card-grid">
          <div className="machine-card-main">
            <section className="machine-card-facts">
              <div>
                <span className="machine-card-fact-icon" aria-hidden="true">
                  ⧉
                </span>
                <p className="muted">{t('detail.deliveryMachine')}</p>
                <strong>{machineName}</strong>
              </div>
              <div>
                <span className="machine-card-fact-icon" aria-hidden="true">
                  ▦
                </span>
                <p className="muted">{t('detail.cardId')}</p>
                <strong>{cardCode}</strong>
              </div>
              <div>
                <span className="machine-card-fact-icon" aria-hidden="true">
                  ⏱
                </span>
                <p className="muted">{t('detail.enteredStage')}</p>
                <strong>{enteredAt ? formatRunTime(enteredAt) : '—'}</strong>
              </div>
            </section>

            <section className="machine-card-suggestion">
              <div className="machine-card-suggestion-copy">
                <span className="machine-card-suggestion-icon" aria-hidden="true">
                  ✦
                </span>
                <div>
                  <h3>{t('detail.suggestionTitle')}</h3>
                  <p>{recommendationReason || summary || t('detail.suggestionDefault')}</p>
                </div>
              </div>
              <span className="machine-card-suggestion-chevron" aria-hidden="true">
                ›
              </span>
            </section>

            <p className="machine-card-handoff">
              <span aria-hidden="true">✋</span> {t('detail.handoff')}
            </p>

            {inProgress ? <WaitLive startedAt={latestCurrentRun?.created_at ?? card.updated_at} variant="banner" /> : null}
            {placeholderRun && !inProgress ? (
              <p className="notice" role="status">
                {PLACEHOLDER_RUN_HINT}
              </p>
            ) : null}

            {card.body.trim() ? (
              <section className="machine-card-body">
                <MarkdownPreview source={card.body} />
              </section>
            ) : null}

            {summary && recommendationReason ? (
              <section>
                <h3>
                  Current handoff · {currentStageLabel}
                  {llm ? ` · ${llm}` : ''}
                </h3>
                <MarkdownPreview source={summary} />
              </section>
            ) : null}

            {waitingWrites ? (
              <section className="agent-decision">
                <h3>Pending writes</h3>
                <p className="muted">This stage confirms MCP writes before they run. Reads already happened.</p>
                {pendingWrites.length ? <pre className="log">{JSON.stringify(pendingWrites, null, 2)}</pre> : <p className="muted">No payload listed.</p>}
              </section>
            ) : null}

            {waiting && recommendation ? (
              <section className={`agent-decision is-${recommendation}`}>
                <h3>Agent recommendation</h3>
                <p className="handoff">
                  {recommendation === 'approve' ? 'Approve' : 'Reject'}
                  {recommendationReason ? ` — ${recommendationReason}` : ''}
                </p>
                <p className="muted">Advisory only. A human still has to confirm before the card moves.</p>
                {reasonCompare === 'same' && /jira/i.test(recommendationReason) ? (
                  <p className="notice" role="status">
                    Same {recommendation} reason as the previous run on this column.
                  </p>
                ) : null}
                {plugins.allowlist.length === 0 || (plugins.jiraConnector && !plugins.allowlist.includes('jira') && !plugins.attached.includes('jira')) ? (
                  <p className="muted">
                    This run had no Jira plugin. Open <strong>Agent</strong> on {currentStageLabel}, check <strong>jira</strong>, save, then rerun.
                  </p>
                ) : null}
              </section>
            ) : null}

            {links.length ? (
              <section>
                <h3>Links</h3>
                <div className="links">
                  {links.map((link) => {
                    const href = safeHttpUrl(link);
                    return href ? (
                      <a key={link} href={href} target="_blank" rel="noreferrer">
                        {link}
                      </a>
                    ) : (
                      <span key={link}>{link}</span>
                    );
                  })}
                </div>
              </section>
            ) : null}

            {expandedStageId ? (
              <JourneyStageDetail stageId={expandedStageId} board={board} runs={runs.filter((run) => run.stage_id === expandedStageId)} />
            ) : null}

            {latestCurrentRun && sandbox ? (
              <p className="muted">
                Workspace copy{llm ? ` · ${llm}` : ''}: {String((latestCurrentRun.inputs?.sandbox as Record<string, unknown> | undefined)?.path || sandbox)}
              </p>
            ) : null}

            <section className="machine-card-journey">
              <div className="machine-card-journey-head">
                <h3>{t('detail.journey')}</h3>
                {onOpenHistory ? (
                  <button type="button" className="btn btn-ghost btn-compact" onClick={onOpenHistory}>
                    {t('detail.fullHistory')}
                  </button>
                ) : null}
              </div>
              <ol className="journey-rail">
                {journey.map((step) => (
                  <li key={step.stage.id} className={`journey-rail-item is-${step.state}`}>
                    <span className="journey-rail-dot" aria-hidden="true" />
                    <div>
                      <p className="journey-rail-time">
                        {step.latestRun
                          ? formatRunTime(step.latestRun.completed_at ?? step.latestRun.created_at)
                          : pathStateLabel({ state: step.state } as StagePathNode, t)}
                      </p>
                      <strong>
                        {step.stage.name}
                        {step.stage.lane != null && (board?.stages.filter((stage) => stage.order === step.stage.order).length ?? 0) > 1
                          ? ` ${t('detail.inParallel')}`
                          : ''}
                      </strong>
                      <span className="muted">{journeyStateLabel(step.state)}</span>
                    </div>
                  </li>
                ))}
              </ol>
            </section>

            {runMutation.isError ? <div className="error">{runErrorMessage(runMutation.error)}</div> : null}
            {writeMutation.isError ? <div className="error">{runErrorMessage(writeMutation.error)}</div> : null}
            {approvalMutation.isError ? <div className="error">{runErrorMessage(approvalMutation.error)}</div> : null}
          </div>

          <aside className="machine-card-actions">
            <h3>{t('detail.actionsTitle')}</h3>

            {canRun ? (
              <button
                type="button"
                className="action-tile is-run"
                onClick={() => {
                  setRunStarted(true);
                  runMutation.mutate();
                }}
                disabled={runMutation.isPending || runStarted}
              >
                <span className="action-tile-icon" aria-hidden="true">
                  ▶
                </span>
                <span>
                  <strong>{t('detail.runStage')}</strong>
                  <small>{currentStageLabel}</small>
                </span>
              </button>
            ) : null}

            {waitingWrites ? (
              <>
                <button type="button" className="action-tile is-approve" onClick={() => writeMutation.mutate(true)} disabled={writeMutation.isPending}>
                  <span className="action-tile-icon" aria-hidden="true">
                    ✓
                  </span>
                  <span>
                    <strong>{t('detail.confirmWrites')}</strong>
                    <small>{t('detail.approveHint')}</small>
                  </span>
                </button>
                <button type="button" className="action-tile is-reject" onClick={() => writeMutation.mutate(false)} disabled={writeMutation.isPending}>
                  <span className="action-tile-icon" aria-hidden="true">
                    ×
                  </span>
                  <span>
                    <strong>{t('detail.declineWrites')}</strong>
                    <small>{t('detail.rejectHint')}</small>
                  </span>
                </button>
              </>
            ) : null}

            {waiting ? (
              <>
                <button
                  type="button"
                  className={`action-tile is-approve${recommendation === 'approve' ? ' is-recommended' : ''}`}
                  onClick={() => approvalMutation.mutate(true)}
                  disabled={approvalMutation.isPending}
                >
                  <span className="action-tile-icon" aria-hidden="true">
                    ✓
                  </span>
                  <span>
                    <strong>{approveLabel(approveLines, board, handoff) || t('detail.approveTitle')}</strong>
                    <small>{t('detail.approveHint')}</small>
                  </span>
                </button>
                <button
                  type="button"
                  className={`action-tile is-reject${recommendation === 'reject' ? ' is-recommended' : ''}`}
                  onClick={() => approvalMutation.mutate(false)}
                  disabled={approvalMutation.isPending}
                >
                  <span className="action-tile-icon" aria-hidden="true">
                    ×
                  </span>
                  <span>
                    <strong>{rejectLabel(rejectLines, board, handoff) || t('detail.rejectTitle')}</strong>
                    <small>{t('detail.rejectHint')}</small>
                  </span>
                </button>
              </>
            ) : null}

            <button
              type="button"
              className="action-tile is-ask"
              onClick={() => {
                setAskNotice('');
                setAskOpen((open) => !open);
              }}
              disabled={askMutation.isPending}
            >
              <span className="action-tile-icon" aria-hidden="true">
                ?
              </span>
              <span>
                <strong>{t('detail.askAgentTitle')}</strong>
                <small>{t('detail.askAgentHint')}</small>
              </span>
            </button>
            {askOpen ? (
              practiceMode ? (
                <p className="notice" role="status">
                  {t('detail.askAgentPractice')}
                </p>
              ) : (
                <form
                  className="ask-agent-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    const question = askText.trim();
                    if (!question || askMutation.isPending) {
                      return;
                    }
                    if (!(
                      card.status === 'idle' ||
                      card.status === 'blocked' ||
                      card.status === 'waiting_approval' ||
                      card.status === 'waiting_tool_approval'
                    )) {
                      setAskNotice(t('detail.askAgentBusy'));
                      return;
                    }
                    askMutation.mutate(question);
                  }}
                >
                  <label className="field">
                    {t('detail.askAgentTitle')}
                    <textarea
                      className="input"
                      rows={3}
                      value={askText}
                      onChange={(event) => setAskText(event.target.value)}
                      placeholder={t('detail.askAgentPlaceholder')}
                      disabled={askMutation.isPending}
                    />
                  </label>
                  <div className="ask-agent-actions">
                    <button type="submit" className="btn btn-primary" disabled={!askText.trim() || askMutation.isPending}>
                      {askMutation.isPending ? t('detail.askAgentRunning') : t('detail.askAgentSend')}
                    </button>
                    <button
                      type="button"
                      className="btn"
                      disabled={askMutation.isPending}
                      onClick={() => {
                        setAskOpen(false);
                        setAskText('');
                      }}
                    >
                      {t('detail.askAgentCancel')}
                    </button>
                  </div>
                </form>
              )
            ) : null}
            {askNotice ? (
              <p className="notice" role="status">
                {askNotice}
              </p>
            ) : null}

            {joining ? <p className="muted">{t('detail.joiningStatus')}</p> : null}
            {inProgress ? <WaitLive startedAt={latestCurrentRun?.created_at ?? card.updated_at} variant="footer" /> : null}
            {!canRun && !waiting && !waitingWrites && !joining && !inProgress ? <p className="muted">{STATUS_LABEL[card.status]}</p> : null}

            <section className="machine-card-writes">
              <h4>
                <span aria-hidden="true">📄</span> {t('detail.writeRecords')}
              </h4>
              {pendingWrites.length ? <pre className="log">{JSON.stringify(pendingWrites, null, 2)}</pre> : <p>{t('detail.noWrites')}</p>}
            </section>
          </aside>
        </div>
      </article>
    </Dialog>
  );
}

function JourneyStageDetail({ stageId, board, runs }: { stageId: string; board?: BoardDetail; runs: AgentRun[] }) {
  const ordered = runsForStage(runs, stageId);
  const finalized = latestFinalizedForStage(ordered, stageId);
  const summary = handoffSummary(finalized);
  const latest = ordered.length ? ordered[ordered.length - 1] : undefined;

  return (
    <div className="journey-detail">
      <p className="journey-detail-kicker">
        {stageName(board, stageId)}
        {finalized ? ` · ${formatRunTime(finalized.completed_at ?? finalized.created_at)}` : ''}
      </p>
      {summary ? <MarkdownPreview source={summary} /> : <p className="muted">No handoff for this stage.</p>}
      {latest?.model_output ? (
        <details className="disclosure">
          <summary>Run log</summary>
          <pre className="log">{latest.model_output}</pre>
        </details>
      ) : null}
    </div>
  );
}

function pendingWriteCalls(run?: AgentRun): Array<Record<string, unknown>> {
  const raw = run?.inputs?.pending_writes;
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object');
}

function runErrorMessage(error: unknown): string {
  if (!(error instanceof Error)) {
    return 'Could not start this stage.';
  }
  try {
    const parsed = JSON.parse(error.message) as { detail?: unknown };
    if (typeof parsed.detail === 'string' && parsed.detail.trim()) {
      return parsed.detail;
    }
  } catch {
    /* response body was not JSON */
  }
  return error.message || 'Could not start this stage.';
}

function gateComment(approved: boolean, recommendation: 'approve' | 'reject' | null): string {
  const action = approved ? 'Approved' : 'Rejected';
  if (!recommendation) {
    return `${action} in UI`;
  }
  const agreed = (approved && recommendation === 'approve') || (!approved && recommendation === 'reject');
  return agreed ? `${action} in UI (confirmed agent ${recommendation})` : `${action} in UI (overrode agent ${recommendation})`;
}

function shortId(id: string): string {
  return id.slice(0, 8).toUpperCase();
}

function detailStatus(
  status: Card['status'],
  t: (key: Parameters<ReturnType<typeof useI18n>['t']>[0], vars?: Record<string, string | number>) => string
): string {
  switch (status) {
    case 'waiting_approval':
      return t('detail.waitingConfirm');
    case 'waiting_tool_approval':
      return t('detail.confirmWriteStatus');
    case 'running':
      return t('detail.inProgress');
    case 'blocked':
      return t('detail.blockedStatus');
    case 'done':
      return t('detail.doneStatus');
    case 'waiting_join':
      return t('detail.joiningStatus');
    default:
      return t('detail.idleStatus');
  }
}

function pathGlyph(node: StagePathNode): string {
  if (node.kind === 'soft_join') {
    return node.state === 'done' ? '✓' : '🔒';
  }
  if (node.kind === 'end') {
    return node.state === 'done' ? '✓' : '○';
  }
  if (node.state === 'done') {
    return '✓';
  }
  if (node.state === 'current' || node.state === 'running') {
    return '●';
  }
  if (node.state === 'failed') {
    return '!';
  }
  return '○';
}

function pathStateLabel(node: Pick<StagePathNode, 'state' | 'kind'> | StagePathNode, t: ReturnType<typeof useI18n>['t']): string {
  if (node.kind === 'soft_join' && node.state === 'locked') {
    return t('detail.softJoinWait');
  }
  switch (node.state) {
    case 'done':
      return t('detail.completed');
    case 'current':
    case 'running':
      return t('detail.current');
    case 'waiting':
    case 'locked':
      return t('detail.softJoinWait');
    case 'failed':
      return t('detail.blockedStatus');
    default:
      return node.kind === 'end' || node.state === 'pending' ? t('detail.notReached') : t('detail.pending');
  }
}

function pathNodeTitle(node: StagePathNode, t: ReturnType<typeof useI18n>['t']): string {
  return `${node.label} · ${pathStateLabel(node, t)}`;
}
