import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '../api/client';
import { Card, Stage } from '../types';
import { CardItem } from './CardItem';

interface Props {
  boardId: string;
  stage: Stage;
  cards: Card[];
  isFirst: boolean;
  row?: number;
  parallel?: boolean;
  openCardId: string | null;
  onOpenCard: (card: Card) => void;
  onOpenConfig: (stage: Stage) => void;
}

export function Column({ boardId, stage, cards, isFirst, row = 1, parallel = false, openCardId, onOpenCard, onOpenConfig }: Props) {
  return (
    <section className={`column${parallel ? ' is-parallel-row' : ''}`}>
      <header className="column-head">
        <div>
          <h2>{stage.name}</h2>
          <p>
            {parallel ? `Row ${row} · parallel` : `Row ${row}`}
            {' · '}
            {stage.require_approval ? 'Human gate' : 'Auto-advance'}
          </p>
        </div>
        <div className="column-actions">
          <span className="column-count">{cards.length}</span>
          <button type="button" className="btn btn-icon" title="Configure agent" onClick={() => onOpenConfig(stage)}>
            Agent
          </button>
        </div>
      </header>
      {isFirst ? <AddCard boardId={boardId} /> : null}
      {cards.map((card) => (
        <CardItem key={card.id} card={card} isOpen={openCardId === card.id} onOpen={onOpenCard} />
      ))}
      {!cards.length ? <div className="empty-col">No cards in this station.</div> : null}
    </section>
  );
}

function AddCard({ boardId }: { boardId: string }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [newCard, setNewCard] = useState({ title: '', body: '' });

  const createCard = useMutation({
    mutationFn: async () => apiClient.post(`/boards/${boardId}/cards`, newCard),
    onSuccess: () => {
      setNewCard({ title: '', body: '' });
      setOpen(false);
      queryClient.invalidateQueries({ queryKey: ['board', boardId] });
    }
  });

  if (!open) {
    return (
      <button type="button" className="add-toggle" onClick={() => setOpen(true)}>
        Add card to this station
      </button>
    );
  }

  return (
    <form
      className="add-card"
      onSubmit={(event) => {
        event.preventDefault();
        if (newCard.title) {
          createCard.mutate();
        }
      }}
    >
      <label className="field">
        Title
        <input
          className="input"
          value={newCard.title}
          onChange={(event) => setNewCard((current) => ({ ...current, title: event.target.value }))}
          placeholder="Card title"
          autoFocus
        />
      </label>
      <label className="field">
        Body
        <textarea
          className="textarea"
          rows={3}
          value={newCard.body}
          onChange={(event) => setNewCard((current) => ({ ...current, body: event.target.value }))}
          placeholder="Markdown body"
        />
      </label>
      <div className="new-board">
        <button type="submit" className="btn btn-primary" disabled={!newCard.title || createCard.isPending}>
          {createCard.isPending ? 'Adding…' : 'Add card'}
        </button>
        <button type="button" className="btn btn-ghost" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
    </form>
  );
}
