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
  const [workspacePath, setWorkspacePath] = useState('');
  const [gitUrl, setGitUrl] = useState('');

  const createBoard = useMutation({
    mutationFn: async () =>
      apiClient.post<BoardSummary>('/boards', {
        name: boardName,
        description: 'Initial Norns board',
        workspace_path: workspacePath,
        git_url: gitUrl
      }),
    onSuccess: (board) => {
      queryClient.invalidateQueries({ queryKey: ['boards'] });
      setBoardName('Default board');
      setWorkspacePath('');
      setGitUrl('');
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
        <div>
          <h1>Settings</h1>
          <p>Create a board for one git repo. Each column Agent can override that repo. Add DeepSeek, OpenAI, or Cursor so stage runs call a real model.</p>
        </div>
      </div>

      <form className="panel" onSubmit={onSubmit}>
        <h2>New board</h2>
        <label className="field">
          Name
          <input className="input" value={boardName} onChange={(event) => setBoardName(event.target.value)} placeholder="Board name" />
        </label>
        <label className="field">
          Git checkout path
          <input className="input" value={workspacePath} onChange={(event) => setWorkspacePath(event.target.value)} placeholder="/home/you/my-repo" />
        </label>
        <label className="field">
          Git remote URL
          <input className="input" value={gitUrl} onChange={(event) => setGitUrl(event.target.value)} placeholder="https://github.com/org/repo" />
        </label>
        <p className="muted">One board, one repo. Stage agents inherit this workspace unless you set a different path on the column Agent.</p>
        <button type="submit" className="btn btn-primary" disabled={!boardName || createBoard.isPending}>
          {createBoard.isPending ? 'Creating…' : 'Create board'}
        </button>
      </form>

      <ConnectorHealth />
    </div>
  );
}
