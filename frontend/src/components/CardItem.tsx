import { Card } from '../types';
import { STATUS_LABEL } from '../status';

interface Props {
  card: Card;
  isOpen: boolean;
  onOpen: (card: Card) => void;
}

export function CardItem({ card, isOpen, onOpen }: Props) {
  return (
    <button type="button" className={`card status-${card.status}${isOpen ? ' is-open' : ''}`} onClick={() => onOpen(card)}>
      <div className="card-top">
        <strong>{card.title}</strong>
        <span className={`status status-${card.status}`}>{STATUS_LABEL[card.status]}</span>
      </div>
      {card.external_id ? <div className="card-ext">{card.external_id}</div> : null}
      {card.status === 'running' ? <div className="card-live">Agent running this stage</div> : null}
      {card.status === 'waiting_approval' ? <div className="card-live">Your turn — review the handoff</div> : null}
      {card.status === 'blocked' ? <div className="card-live">Blocked — run again when ready</div> : null}
    </button>
  );
}
