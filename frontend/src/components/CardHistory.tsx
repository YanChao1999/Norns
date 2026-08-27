import { useQuery } from '@tanstack/react-query';

import { apiClient } from '../api/client';
import { buildJourney, chronologicalRuns, compareRunDecision, diagramSvg, formatRunTime, handoffSummary, isFinalizedRun, journeyStateLabel, llmLabel, pluginsSnapshot, runDecision, stageName } from '../cardJourney';
import { Handoff } from '../gateLabels';
import { AgentRun, BoardDetail, Card } from '../types';

interface Props {
  card: Card;
  board: BoardDetail;
  onBack: () => void;
  onOpenCard: () => void;
}

export function CardHistory({ card, board, onBack, onOpenCard }: Props) {
  const { data: runs = [], isLoading } = useQuery({
    queryKey: ['runs', card.id],
    queryFn: () => apiClient.get<AgentRun[]>(`/cards/${card.id}/runs`)
  });

  const journey = buildJourney(card, board, runs);
  const timeline = chronologicalRuns(runs);

  return (
    <div className="history-page">
      <div className="history-head">
        <div>
          <p className="drawer-kicker">Card history</p>
          <h1>{card.title}</h1>
          <p className="muted">Full stage path and every agent run. Open the card drawer for gate actions on the current stage.</p>
        </div>
        <div className="history-actions">
          <button type="button" className="btn btn-ghost" onClick={onBack}>
            Back to board
          </button>
          <button type="button" className="btn btn-primary" onClick={onOpenCard}>
            Open card
          </button>
        </div>
      </div>

      <section className="history-section">
        <h2>Journey</h2>
        <ol className="journey-list">
          {journey.map((step) => (
            <li key={step.stage.id} className={`journey-step is-${step.state}`}>
              <div className="journey-step-head">
                <span className="journey-step-name">{step.stage.name}</span>
                <span className={`journey-pill is-${step.state}`}>{journeyStateLabel(step.state)}</span>
              </div>
              {step.latestRun ? (
                <p className="muted">
                  {step.runs.length} run{step.runs.length === 1 ? '' : 's'} · last {formatRunTime(step.latestRun.completed_at ?? step.latestRun.created_at)}
                </p>
              ) : (
                <p className="muted">No runs yet</p>
              )}
            </li>
          ))}
        </ol>
      </section>

      <section className="history-section">
        <h2>Run timeline</h2>
        {isLoading ? <p className="muted">Loading runs…</p> : null}
        {!isLoading && !timeline.length ? <p className="muted">No agent runs for this card yet.</p> : null}
        <div className="history-timeline">
          {timeline.map((run, index) => {
            const handoff = (run.handoff ?? {}) as Handoff;
            const summary = handoffSummary(run);
            const links = Array.isArray(handoff.links) ? handoff.links : [];
            const plantuml = diagramSvg(handoff);
            const previous = timeline
              .slice(0, index)
              .reverse()
              .find((item) => item.stage_id === run.stage_id) ?? null;
            const compare = compareRunDecision(run, previous);
            const decision = runDecision(run);
            const plugins = pluginsSnapshot(run);
            return (
              <article key={run.id} className={`history-run is-${run.status}`}>
                <header className="history-run-head">
                  <div>
                    <h3>{stageName(board, run.stage_id)}</h3>
                    <p className="muted">
                      {run.status}
                      {isFinalizedRun(run) ? ' · finalized' : ''}
                      {' · '}
                      {formatRunTime(run.created_at)}
                      {run.completed_at ? ` → ${formatRunTime(run.completed_at)}` : ''}
                      {llmLabel(run) ? ` · ${llmLabel(run)}` : ''}
                    </p>
                  </div>
                  {decision.recommendation ? (
                    <span className={`journey-pill is-${decision.recommendation === 'reject' ? 'failed' : 'done'}`}>
                      {decision.recommendation}
                    </span>
                  ) : null}
                </header>
                {decision.reason ? <p className="handoff">{decision.reason}</p> : null}
                {compare === 'same' ? (
                  <p className="notice" role="status">
                    Same {decision.recommendation || 'decision'} as the previous {stageName(board, previous?.stage_id || run.stage_id)} run
                    {previous ? ` (${formatRunTime(previous.completed_at ?? previous.created_at)})` : ''}.
                  </p>
                ) : null}
                {compare === 'changed' && previous ? (
                  <p className="muted">
                    Different from the previous run
                    {runDecision(previous).reason ? `: “${runDecision(previous).reason}”` : ''}.
                  </p>
                ) : null}
                <p className="muted">
                  Plugins: {plugins.attached.length ? plugins.attached.join(', ') : plugins.allowlist.length ? plugins.allowlist.join(', ') : 'none'}
                  {plugins.jiraConnector === false ? ' · Jira connector not active in Settings' : ''}
                  {plugins.jiraConnector === true && !plugins.attached.includes('jira') && !plugins.allowlist.includes('jira')
                    ? ' · Jira connector is on, but this column Agent did not enable jira'
                    : ''}
                </p>
                {summary && summary !== decision.reason ? <p className="handoff">{summary}</p> : !decision.reason ? <p className="muted">No handoff summary.</p> : null}
                {links.length ? (
                  <div className="links">
                    {links.map((link) => (
                      <a key={link} href={link} target="_blank" rel="noreferrer">
                        {link}
                      </a>
                    ))}
                  </div>
                ) : null}
                {plantuml ? (
                  <iframe
                    sandbox=""
                    srcDoc={`<!DOCTYPE html><html><head><meta charset="utf-8"><style>html,body{margin:0;background:#fff}</style></head><body>${plantuml}</body></html>`}
                    title={`PlantUML ${run.id}`}
                    className="preview-frame"
                  />
                ) : null}
                {run.model_output ? (
                  <details className="disclosure">
                    <summary>Full run log</summary>
                    <pre className="log">{run.model_output}</pre>
                  </details>
                ) : null}
                {run.tool_calls?.length ? (
                  <details className="disclosure">
                    <summary>Tool calls</summary>
                    <pre className="log">{JSON.stringify(run.tool_calls, null, 2)}</pre>
                  </details>
                ) : null}
              </article>
            );
          })}
        </div>
      </section>
    </div>
  );
}
