import { cardFaceSummary } from '../cardPreview';
import { PRACTICE_WAITING_HINT } from '../runHints';
import { Card } from '../types';
import { STATUS_LABEL } from '../status';
import { WaitLive } from './WaitLive';

interface Props {
  card: Card;
  isOpen: boolean;
  isParallelLane?: boolean;
  onOpen: (card: Card) => void;
}

export function CardItem({ card, isOpen, isParallelLane = false, onOpen }: Props) {
  const summary = cardFaceSummary(card.body, {
    recommendation: card.recommendation,
    reason: card.recommendation_reason
  });
  const practice = Boolean(card.practice);
  return (
    <button type="button" className={`card status-${card.status}${isOpen ? ' is-open' : ''}${practice ? ' is-practice' : ''}`} onClick={() => onOpen(card)}>
      <div className="card-top">
        <strong>{card.title}</strong>
        <span className={`status status-${card.status}`}>{practice && card.status === 'waiting_approval' ? 'practice wait' : STATUS_LABEL[card.status]}</span>
      </div>
      {practice ? <div className="card-ext">Practice</div> : null}
      {card.external_id ? <div className="card-ext">{card.external_id}</div> : null}
      {summary ? <p className="card-body">{summary}</p> : null}
      {card.status === 'running' ? <WaitLive startedAt={card.updated_at} /> : null}
      {card.status === 'waiting_approval' ? (
        <div className="card-live">{practice ? PRACTICE_WAITING_HINT : 'Your turn — confirm the agent\u2019s approve or reject'}</div>
      ) : null}
      {card.status === 'waiting_tool_approval' ? <div className="card-live">Your turn — confirm this write before it runs</div> : null}
      {card.status === 'blocked' ? <div className="card-live">Blocked — run again when ready</div> : null}
      {card.status === 'waiting_join' ? <div className="card-live">Legacy join wait (unused)</div> : null}
      {isParallelLane && card.parent_card_id ? <div className="card-live">Parallel track</div> : null}
    </button>
  );
}
