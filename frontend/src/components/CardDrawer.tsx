import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '../api/client';
import {
  buildJourney,
  compareRunDecision,
  diagramSvg,
  formatRunTime,
  handoffSummary,
  journeyStateLabel,
  latestFinalizedForStage,
  llmLabel,
  pluginsSnapshot,
  runsForStage,
  safeHttpUrl,
  sandboxLabel,
  stageName
} from '../cardJourney';
import { Handoff, approveLabel, rejectLabel } from '../gateLabels';
import { PLACEHOLDER_RUN_HINT, PRACTICE_APPROVE_LABEL, PRACTICE_REJECT_LABEL, isPlaceholderRun } from '../runHints';
import { STATUS_LABEL } from '../status';
import { AgentRun, BoardDetail, Card } from '../types';
import { Dialog } from './Dialog';
import { MarkdownPreview } from './MarkdownPreview';
import { WaitLive } from './WaitLive';

interface Props {
  card: Card | null;
  board?: BoardDetail;
  onClose: () => void;
  onOpenHistory?: () => void;
}

function agentRecommendation(value: unknown): 'approve' | 'reject' | null {
  return value === 'approve' || value === 'reject' ? value : null;
}

export function CardDrawer({ card, board, onClose, onOpenHistory }: Props) {
  const queryClient = useQueryClient();
  const previousStatus = useRef<{ id?: string; status?: string }>({});
  const [runStarted, setRunStarted] = useState(false);
  const [expandedStageId, setExpandedStageId] = useState<string | null>(null);

  const { data: runs = [] } = useQuery({
    enabled: Boolean(card),
    queryKey: ['runs', card?.id],
    queryFn: () => apiClient.get<AgentRun[]>(`/cards/${card?.id}/runs`),
    refetchInterval: card?.status === 'running' || card?.status === 'waiting_tool_approval' ? 2000 : false
  });

  useEffect(() => {
    setRunStarted(false);
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

  const journey = useMemo(() => (card ? buildJourney(card, board, runs) : []), [board, card, runs]);

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
  const plantuml = diagramSvg(handoff);
  const pendingWrites = pendingWriteCalls(latestCurrentRun);
  const placeholderRun = isPlaceholderRun(handoffRun ?? latestCurrentRun);
  const summary = handoffSummary(handoffRun);
  const links = Array.isArray(handoff.links) ? handoff.links : [];
  const recommendation = agentRecommendation(handoff.recommendation);
  const recommendationReason = typeof handoff.recommendation_reason === 'string' ? handoff.recommendation_reason.trim() : '';
  const reasonCompare = latestCurrentRun ? compareRunDecision(latestCurrentRun, previousCurrentRun) : 'first';
  const plugins = pluginsSnapshot(latestCurrentRun);
  const llm = llmLabel(latestCurrentRun);
  const sandbox = sandboxLabel(latestCurrentRun);
  const outgoing = (board?.transitions ?? []).filter((edge) => edge.from_stage_id === card.current_stage_id);
  const approveLines = outgoing.filter((edge) => edge.event === 'approve');
  const rejectLines = outgoing.filter((edge) => edge.event === 'reject');
  const currentStageLabel = stageName(board, currentStageId);
  const pastSteps = journey.filter((step) => step.state === 'done' || step.state === 'failed');

  return (
    <Dialog open onClose={onClose} labelledBy="card-drawer-title" variant="drawer">
      <header className="drawer-head">
        <div>
          {card.external_id ? <p className="drawer-kicker">{card.external_id}</p> : null}
          <h2 id="card-drawer-title">{card.title}</h2>
        </div>
        <button type="button" className="btn btn-ghost" onClick={onClose}>
          Close
        </button>
      </header>

      <div className="drawer-body">
        <span className={`status status-${card.status}`}>{STATUS_LABEL[card.status]}</span>

        <section className="journey-panel">
          <div className="journey-panel-head">
            <h3>Journey</h3>
            {onOpenHistory ? (
              <button type="button" className="btn btn-ghost btn-compact" onClick={onOpenHistory}>
                Full history
              </button>
            ) : null}
          </div>
          <ol className="journey-strip" aria-label="Stage journey">
            {journey.map((step, index) => (
              <li key={step.stage.id} className={`journey-chip is-${step.state}`}>
                {index > 0 ? (
                  <span className="journey-arrow" aria-hidden="true">
                    →
                  </span>
                ) : null}
                <button
                  type="button"
                  className={`journey-chip-btn is-${step.state}`}
                  aria-pressed={expandedStageId === step.stage.id}
                  disabled={step.state === 'pending' && step.runs.length === 0}
                  onClick={() => setExpandedStageId((current) => (current === step.stage.id ? null : step.stage.id))}
                  title={`${step.stage.name} · ${journeyStateLabel(step.state)}`}
                >
                  <span className="journey-chip-name">{step.stage.name}</span>
                  <span className="journey-chip-state">{journeyStateLabel(step.state)}</span>
                </button>
              </li>
            ))}
          </ol>
          {expandedStageId ? (
            <JourneyStageDetail stageId={expandedStageId} board={board} runs={runs.filter((run) => run.stage_id === expandedStageId)} />
          ) : pastSteps.length ? (
            <p className="muted">Select a past stage to review its handoff, or open full history.</p>
          ) : (
            <p className="muted">No prior stages yet. History accumulates as the card advances.</p>
          )}
        </section>

        {inProgress ? <WaitLive startedAt={latestCurrentRun?.created_at ?? card.updated_at} variant="banner" /> : null}
        {placeholderRun && !inProgress ? (
          <p className="notice" role="status">
            {PLACEHOLDER_RUN_HINT}
          </p>
        ) : null}

        <section>
          <h3>Card body</h3>
          {card.body.trim() ? <MarkdownPreview source={card.body} /> : <p className="muted">No markdown body provided.</p>}
        </section>

        <section>
          <h3>
            Current handoff · {currentStageLabel}
            {llm ? ` · ${llm}` : ''}
          </h3>
          {summary ? <MarkdownPreview source={summary} /> : <p className="muted">No stage run yet for this station. Run it to produce a handoff.</p>}
        </section>

        {waitingWrites ? (
          <section className="agent-decision">
            <h3>Pending writes</h3>
            <p className="muted">
              This stage confirms MCP writes before they run. Reads already happened. Confirm to execute these calls, or decline to skip them.
            </p>
            {pendingWrites.length ? (
              <pre className="log">{JSON.stringify(pendingWrites, null, 2)}</pre>
            ) : (
              <p className="muted">No payload listed. Confirming will still clear the wait and re-run the stage.</p>
            )}
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
                Same {recommendation} reason as the previous run on this column. Enabling jira on this column Agent (and an active Jira connector) is required
                before a rerun can create a ticket.
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

        {latestCurrentRun ? (
          <section>
            <h3>
              Run log · {currentStageLabel}
              {llm ? ` · ${llm}` : ''}
              {sandbox ? ` · ${sandbox}` : ''}
            </h3>
            {sandbox && latestCurrentRun?.inputs?.sandbox && typeof latestCurrentRun.inputs.sandbox === 'object' ? (
              <p className="muted">Workspace copy: {String((latestCurrentRun.inputs.sandbox as Record<string, unknown>).path || '')}</p>
            ) : null}
            {latestCurrentRun.model_output.trim() ? <MarkdownPreview source={latestCurrentRun.model_output} /> : <p className="muted">No model output.</p>}
          </section>
        ) : null}

        {plantuml ? (
          <section>
            <h3>PlantUML preview</h3>
            <iframe
              sandbox=""
              srcDoc={`<!DOCTYPE html><html><head><meta charset="utf-8"><style>html,body{margin:0;background:#fff}</style></head><body>${plantuml}</body></html>`}
              title="PlantUML preview"
              className="preview-frame"
            />
          </section>
        ) : null}

        {latestCurrentRun ? (
          <details className="disclosure">
            <summary>Raw tool calls and handoff JSON</summary>
            <pre className="log">{JSON.stringify({ tool_calls: latestCurrentRun.tool_calls, handoff: latestCurrentRun.handoff }, null, 2)}</pre>
          </details>
        ) : null}
        {runMutation.isError ? <div className="error">{runErrorMessage(runMutation.error)}</div> : null}
        {writeMutation.isError ? <div className="error">{runErrorMessage(writeMutation.error)}</div> : null}
        {approvalMutation.isError ? <div className="error">{runErrorMessage(approvalMutation.error)}</div> : null}
      </div>

      <footer className="drawer-foot">
        {canRun ? (
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              setRunStarted(true);
              runMutation.mutate();
            }}
            disabled={runMutation.isPending || runStarted}
          >
            {runMutation.isPending ? 'Starting…' : 'Run this stage'}
          </button>
        ) : null}
        {waitingWrites ? (
          <>
            <button type="button" className="btn btn-gate" onClick={() => writeMutation.mutate(true)} disabled={writeMutation.isPending}>
              Confirm writes
            </button>
            <button type="button" className="btn btn-danger" onClick={() => writeMutation.mutate(false)} disabled={writeMutation.isPending}>
              Decline writes
            </button>
          </>
        ) : null}
        {waiting ? (
          <>
            <button
              type="button"
              className={`btn btn-gate${recommendation === 'approve' ? ' is-recommended' : ''}`}
              onClick={() => approvalMutation.mutate(true)}
              disabled={approvalMutation.isPending}
              title={
                placeholderRun
                  ? 'Practice approve — continues the practice path only'
                  : recommendation === 'approve'
                    ? 'Agent recommended approve'
                    : 'Confirm approve'
              }
            >
              {placeholderRun ? PRACTICE_APPROVE_LABEL : approveLabel(approveLines, board, handoff)}
              {!placeholderRun && recommendation === 'approve' ? ' · agent' : ''}
            </button>
            <button
              type="button"
              className={`btn btn-danger${recommendation === 'reject' ? ' is-recommended' : ''}`}
              onClick={() => approvalMutation.mutate(false)}
              disabled={approvalMutation.isPending}
              title={
                placeholderRun ? 'Practice reject — blocks the practice card' : recommendation === 'reject' ? 'Agent recommended reject' : 'Confirm reject'
              }
            >
              {placeholderRun ? PRACTICE_REJECT_LABEL : rejectLabel(rejectLines, board, handoff)}
              {!placeholderRun && recommendation === 'reject' ? ' · agent' : ''}
            </button>
          </>
        ) : null}
        {joining ? <span className="muted">Legacy waiting_join status — new boards run converging stages independently.</span> : null}
        {inProgress ? <WaitLive startedAt={latestCurrentRun?.created_at ?? card.updated_at} variant="footer" /> : null}
        {!canRun && !waiting && !waitingWrites && !joining && !inProgress ? <span className="muted">No gate action on this card.</span> : null}
      </footer>
    </Dialog>
  );
}

function JourneyStageDetail({ stageId, board, runs }: { stageId: string; board?: BoardDetail; runs: AgentRun[] }) {
  const ordered = runsForStage(runs, stageId);
  const finalized = latestFinalizedForStage(ordered, stageId);
  const summary = handoffSummary(finalized);
  const plantuml = finalized ? diagramSvg((finalized.handoff ?? {}) as Handoff) : undefined;
  const latest = ordered.length ? ordered[ordered.length - 1] : undefined;

  return (
    <div className="journey-detail">
      <p className="journey-detail-kicker">
        {stageName(board, stageId)}
        {finalized ? ` · ${formatRunTime(finalized.completed_at ?? finalized.created_at)}` : ''}
      </p>
      {summary ? <MarkdownPreview source={summary} /> : <p className="muted">No handoff for this stage.</p>}
      {plantuml ? (
        <iframe
          sandbox=""
          srcDoc={`<!DOCTYPE html><html><head><meta charset="utf-8"><style>html,body{margin:0;background:#fff}</style></head><body>${plantuml}</body></html>`}
          title={`PlantUML ${stageId}`}
          className="preview-frame"
        />
      ) : null}
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
