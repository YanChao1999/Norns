import { MouseEvent, useEffect, useState } from 'react';

import { cardFaceSummary } from '../cardPreview';
import { useCardGates } from '../hooks/useCardGates';
import { useI18n } from '../i18n';
import { PRACTICE_WAITING_HINT } from '../runHints';
import { STATUS_LABEL } from '../status';
import { Card } from '../types';
import { formatElapsed, parseApiTime } from '../waitProgress';
import { WaitLive } from './WaitLive';

interface Props {
  card: Card;
  isOpen: boolean;
  isParallelLane?: boolean;
  locked?: boolean;
  onOpen: (card: Card) => void;
}

export function CardItem({ card, isOpen, isParallelLane = false, locked = false, onOpen }: Props) {
  const { t } = useI18n();
  const { approval, writes } = useCardGates(card.id, card.board_id);
  const summary = cardFaceSummary(card.body, {
    recommendation: card.recommendation,
    reason: card.recommendation_reason
  });
  const waiting = card.status === 'waiting_approval';
  const waitingWrites = card.status === 'waiting_tool_approval';
  const running = card.status === 'running';
  const confirmWrite = waitingWrites;
  const practice = Boolean(card.practice);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!running) {
      return;
    }
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [running, card.updated_at, card.id]);

  const stop = (event: MouseEvent) => {
    event.stopPropagation();
  };

  const startMs = parseApiTime(card.updated_at);
  const elapsed = startMs != null ? formatElapsed(Math.max(0, now - startMs)) : '0:00';

  return (
    <div
      role="button"
      tabIndex={0}
      className={`gate-card is-${card.status}${confirmWrite ? ' is-confirm-write' : ''}${isOpen ? ' is-open' : ''}${locked ? ' is-locked' : ''}${practice ? ' is-practice' : ''}`}
      onClick={() => onOpen(card)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onOpen(card);
        }
      }}
    >
      {confirmWrite ? <span className="gate-card-badge">{t('card.confirmWriteBadge')}</span> : null}
      {practice ? <span className="gate-card-badge is-practice">{t('card.practiceBadge')}</span> : null}

      <div className={`gate-card-status${waiting || waitingWrites ? ' is-waiting' : ''}${running ? ' is-running' : ''}`}>
        {practice && waiting ? t('card.practiceWait') : STATUS_LABEL[card.status]}
        {running ? ` · ${t('card.elapsed')}` : ''}
      </div>

      <div className="gate-card-title">{card.title}</div>
      {practice ? <div className="card-ext">{t('card.practiceLabel')}</div> : null}
      {card.external_id ? <div className="card-ext">{card.external_id}</div> : null}

      {waiting ? (
        <div className="gate-callout is-suggest">
          <strong>{t('card.suggestion')}</strong>
          <span className="muted">{practice ? PRACTICE_WAITING_HINT : summary || card.recommendation_reason || t('card.suggestionDefault')}</span>
        </div>
      ) : null}

      {running ? (
        <div className="gate-callout is-running">
          <div className="gate-timer">
            <span className="muted">{t('card.elapsed')}</span>
            <time dateTime={card.updated_at || undefined}>{elapsed}</time>
          </div>
          <span className="muted">{t('card.runningPolarion')}</span>
          <WaitLive startedAt={card.updated_at} />
        </div>
      ) : null}

      {waitingWrites ? (
        <div className="gate-callout is-write">
          <span>{t('card.confirmWriteHint')}</span>
        </div>
      ) : null}

      {!waiting && !running && !waitingWrites && summary ? <p className="card-body">{summary}</p> : null}

      {card.status === 'blocked' ? <div className="card-live">{t('card.blocked')}</div> : null}
      {card.status === 'waiting_join' ? <div className="card-live">{t('card.waitingJoin')}</div> : null}
      {isParallelLane && card.parent_card_id ? <div className="card-live">{t('card.parallelTrack')}</div> : null}

      {waiting ? (
        <div className="gate-actions" onClick={stop}>
          <button
            type="button"
            className="btn btn-approve"
            disabled={approval.isPending || locked}
            onClick={() =>
              approval.mutate({
                approved: true,
                recommendation: card.recommendation === 'approve' || card.recommendation === 'reject' ? card.recommendation : null
              })
            }
          >
            {practice ? t('practice.approve') : t('card.approve')}
          </button>
          <button
            type="button"
            className="btn btn-reject"
            disabled={approval.isPending || locked}
            onClick={() =>
              approval.mutate({
                approved: false,
                recommendation: card.recommendation === 'approve' || card.recommendation === 'reject' ? card.recommendation : null
              })
            }
          >
            {t('card.reject')}
          </button>
        </div>
      ) : null}

      {waiting ? <p className="gate-footnote">{t('board.approveNeWritten')}</p> : null}

      {waitingWrites ? (
        <div onClick={stop}>
          <button type="button" className="btn btn-confirm-write" disabled={writes.isPending || locked} onClick={() => writes.mutate(true)}>
            {t('board.confirmWrite')}
          </button>
        </div>
      ) : null}
    </div>
  );
}
