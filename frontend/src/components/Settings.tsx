import { FormEvent, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '../api/client';
import { BoardSummary } from '../types';
import { ConnectorHealth } from './ConnectorHealth';

interface Props {
  onCreated: (boardId: string) => void;
}

export function Settings({ onCreated }: Props) {
  const queryClient = useQueryClient();
  const [boardName, setBoardName] = useState('Default board');

  const createBoard = useMutation({
    mutationFn: async () =>
      apiClient.post<BoardSummary>('/boards', {
        name: boardName,
        description: 'Initial Norns board'
      }),
    onSuccess: (board) => {
      queryClient.invalidateQueries({ queryKey: ['boards'] });
      setBoardName('Default board');
      onCreated(board.id);
    }
  });

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (boardName) {
      createBoard.mutate();
    }
  };

  return (
    <div className="settings">
      <div className="board-head">
        <h1>Settings</h1>
        <p>Boards and connector health live here so the board canvas stays clear.</p>
      </div>

      <form className="panel" onSubmit={onSubmit}>
        <h2>New board</h2>
        <label className="field">
          Name
          <input className="input" value={boardName} onChange={(event) => setBoardName(event.target.value)} placeholder="Board name" />
        </label>
        <button type="submit" className="btn btn-primary" disabled={!boardName || createBoard.isPending}>
          {createBoard.isPending ? 'Creating…' : 'Create board'}
        </button>
      </form>

      <ConnectorHealth />
    </div>
  );
}
