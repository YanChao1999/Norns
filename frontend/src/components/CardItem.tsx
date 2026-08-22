import type { CSSProperties } from 'react';

import { Card } from '../types';

const badgeStyles: Record<Card['status'], CSSProperties> = {
  idle: { background: '#e5e7eb', color: '#111827' },
  running: { background: '#dbeafe', color: '#1d4ed8' },
  waiting_approval: { background: '#fef3c7', color: '#92400e' },
  blocked: { background: '#fee2e2', color: '#b91c1c' },
  done: { background: '#dcfce7', color: '#166534' }
};

interface Props {
  card: Card;
  onOpen: (card: Card) => void;
  onDragStart?: (card: Card) => void;
}

export function CardItem({ card, onOpen, onDragStart }: Props) {
  return (
    <div
      draggable={card.status !== 'waiting_approval'}
      onDragStart={() => onDragStart?.(card)}
      onClick={() => onOpen(card)}
      style={{
        border: '1px solid #d1d5db',
        borderRadius: 8,
        padding: 12,
        background: 'white',
        cursor: 'pointer',
        boxShadow: '0 1px 2px rgba(0,0,0,0.05)'
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
        <strong>{card.title}</strong>
        <span style={{ ...badgeStyles[card.status], borderRadius: 999, padding: '2px 8px', fontSize: 12 }}>
          {card.status === 'running' ? 'running ⟳' : card.status.replace('_', ' ')}
        </span>
      </div>
      {card.external_id ? (
        <div style={{ marginTop: 8, color: '#6b7280', fontSize: 12 }}>{card.external_id}</div>
      ) : null}
    </div>
  );
}
