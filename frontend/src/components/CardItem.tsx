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
  return (
    <button type="button" className={`card status-${card.status}${isOpen ? ' is-open' : ''}`} onClick={() => onOpen(card)}>
      <div className="card-top">
        <strong>{card.title}</strong>
        <span className={`status status-${card.status}`}>{STATUS_LABEL[card.status]}</span>
      </div>
      {card.external_id ? <div className="card-ext">{card.external_id}</div> : null}
      {card.status === 'running' ? <WaitLive startedAt={card.updated_at} /> : null}
      {card.status === 'waiting_approval' ? <div className="card-live">Your turn — confirm the agent&apos;s approve or reject</div> : null}
      {card.status === 'waiting_tool_approval' ? <div className="card-live">Your turn — confirm this write before it runs</div> : null}
      {card.status === 'blocked' ? <div className="card-live">Blocked — run again when ready</div> : null}
      {card.status === 'waiting_join' ? <div className="card-live">Waiting for other parallel tracks</div> : null}
      {isParallelLane && card.parent_card_id ? <div className="card-live">Parallel track</div> : null}
    </button>
  );
}
