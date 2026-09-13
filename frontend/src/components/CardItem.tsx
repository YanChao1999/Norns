import { MouseEvent } from 'react';

import { cardFaceSummary } from '../cardPreview';
import { useCardGates } from '../hooks/useCardGates';
import { useI18n } from '../i18n';
import { STATUS_LABEL } from '../status';
import { Card } from '../types';
import { formatElapsed } from '../waitProgress';
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

  const stop = (event: MouseEvent) => {
    event.stopPropagation();
  };

  const elapsed = card.updated_at ? formatElapsed(Math.max(0, Date.now() - Date.parse(card.updated_at))) : '0:00';

  return (
    <div
      role="button"
      tabIndex={0}
      className={`gate-card is-${card.status}${confirmWrite ? ' is-confirm-write' : ''}${isOpen ? ' is-open' : ''}${locked ? ' is-locked' : ''}`}
      onClick={() => onOpen(card)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onOpen(card);
        }
      }}
    >
      {confirmWrite ? <span className="gate-card-badge">{t('card.confirmWriteBadge')}</span> : null}

      <div className={`gate-card-status${waiting || waitingWrites ? ' is-waiting' : ''}${running ? ' is-running' : ''}`}>
        {STATUS_LABEL[card.status]}
        {running ? ` · ${t('card.elapsed')}` : ''}
      </div>

      <div className="gate-card-title">{card.title}</div>
      {card.external_id ? <div className="card-ext">{card.external_id}</div> : null}

      {waiting ? (
        <div className="gate-callout is-suggest">
          <strong>{t('card.suggestion')}</strong>
          <span className="muted">{summary || card.recommendation_reason || t('card.suggestionDefault')}</span>
        </div>
      ) : null}

      {running ? (
        <div className="gate-callout is-running">
          <div className="gate-timer">
            <span className="muted">{t('card.elapsed')}</span>
            <time>{elapsed}</time>
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
            onClick={() => approval.mutate({ approved: true, recommendation: card.recommendation === 'approve' || card.recommendation === 'reject' ? card.recommendation : null })}
          >
            {t('card.approve')}
          </button>
          <button
            type="button"
            className="btn btn-reject"
            disabled={approval.isPending || locked}
            onClick={() => approval.mutate({ approved: false, recommendation: card.recommendation === 'approve' || card.recommendation === 'reject' ? card.recommendation : null })}
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
