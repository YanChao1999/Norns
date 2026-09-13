import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '../api/client';
import { useI18n } from '../i18n';
import { Card, Stage } from '../types';
import { CardItem } from './CardItem';

interface Props {
  boardId: string;
  stage: Stage;
  cards: Card[];
  isFirst: boolean;
  row?: number;
  parallel?: boolean;
  locked?: boolean;
  openCardId: string | null;
  onOpenCard: (card: Card) => void;
  onOpenConfig: (stage: Stage) => void;
  compact?: boolean;
}

export function Column({
  boardId,
  stage,
  cards,
  isFirst,
  row = 1,
  parallel = false,
  locked = false,
  openCardId,
  onOpenCard,
  onOpenConfig,
  compact = false
}: Props) {
  const { t } = useI18n();
  const tools = stage.agent_config?.tool_allowlist?.length ? stage.agent_config.tool_allowlist.join(' · ') : t('board.noPlugins');
  const roleBits = [
    stage.require_approval ? t('board.humanGate') : t('board.autoAdvance'),
    stage.confirm_writes ? t('board.confirmWrites') : null
  ].filter(Boolean);

  return (
    <section className={`station column${parallel ? ' is-parallel-row' : ''}${locked ? ' is-locked' : ''}${compact ? ' is-compact' : ''}`}>
      <header className="station-head column-head">
        <div>
          <h2>{stage.name}</h2>
          <p>
            {parallel ? `${t('board.row', { row })} · ${t('board.parallel')} · ` : ''}
            {roleBits.join(' · ')}
          </p>
          <p className="station-tools">({tools}{stage.agent_config?.workspace_path || stage.agent_config?.git_url ? ` · ${t('board.ownRepo')}` : ''})</p>
        </div>
        <div className="column-actions">
          <span className="column-count">{cards.length}</span>
          <button type="button" className="btn btn-icon" title={t('board.agent')} onClick={() => onOpenConfig(stage)}>
            {t('board.agent')}
          </button>
        </div>
      </header>
      {isFirst && !locked ? <AddCard boardId={boardId} /> : null}
      {locked && stage.confirm_writes ? (
        <div className="locked-panel">
          <div className="locked-panel-icon" aria-hidden="true">
            🔒
          </div>
          <strong>{t('board.skuldWaiting')}</strong>
          <p>{t('board.skuldLocked')}</p>
        </div>
      ) : (
        <>
          {cards.map((card) => (
            <CardItem key={card.id} card={card} isOpen={openCardId === card.id} isParallelLane={parallel} locked={locked} onOpen={onOpenCard} />
          ))}
          {!cards.length ? (
            <div className="station-empty empty-col">
              <span aria-hidden="true">📁</span>
              <span>{t('board.emptyStation')}</span>
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}

function AddCard({ boardId }: { boardId: string }) {
  const { t } = useI18n();
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
        {t('board.addCard')}
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
      <input
        className="input"
        value={newCard.title}
        onChange={(event) => setNewCard((current) => ({ ...current, title: event.target.value }))}
        placeholder="Title"
        autoFocus
      />
      <textarea
        className="input"
        value={newCard.body}
        onChange={(event) => setNewCard((current) => ({ ...current, body: event.target.value }))}
        placeholder="Body (markdown)"
        rows={3}
      />
      <div className="gate-actions">
        <button type="submit" className="btn btn-primary" disabled={!newCard.title || createCard.isPending}>
          Add
        </button>
        <button type="button" className="btn" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
    </form>
  );
}
