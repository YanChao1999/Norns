import { Card, Stage } from '../types';
import { CardItem } from './CardItem';

interface Props {
  stage: Stage;
  cards: Card[];
  onOpenCard: (card: Card) => void;
  onOpenConfig: (stage: Stage) => void;
}

export function Column({ stage, cards, onOpenCard, onOpenConfig }: Props) {
  return (
    <section
      style={{
        minWidth: 300,
        background: '#f8fafc',
        border: '1px solid #e5e7eb',
        borderRadius: 12,
        padding: 16,
        display: 'grid',
        gap: 12
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h3 style={{ margin: 0 }}>{stage.name}</h3>
          <small>{stage.require_approval ? 'Approval required' : 'Auto-advance enabled'}</small>
        </div>
        <button title="Configure agent" onClick={() => onOpenConfig(stage)}>
          ⚙
        </button>
      </div>
      {cards.map((card) => (
        <CardItem key={card.id} card={card} onOpen={onOpenCard} />
      ))}
      {!cards.length ? <div style={{ color: '#94a3b8' }}>No cards in this stage.</div> : null}
    </section>
  );
}
