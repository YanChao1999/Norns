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
          <p>Create a board, then bind its git folder from the board header. Add DeepSeek, OpenAI, or Cursor so stage runs call a real model.</p>
        </div>
      </div>

      <form className="panel" onSubmit={onSubmit}>
        <h2>New board</h2>
        <label className="field">
          Name
          <input className="input" value={boardName} onChange={(event) => setBoardName(event.target.value)} placeholder="Board name" />
        </label>
        <details className="workspace-details">
          <summary>Git repo for this board (optional)</summary>
          <label className="field">
            Folder on this machine
            <input className="input" value={workspacePath} onChange={(event) => setWorkspacePath(event.target.value)} placeholder="/home/you/projects/app" />
          </label>
          <label className="field">
            GitHub or git URL
            <input className="input" value={gitUrl} onChange={(event) => setGitUrl(event.target.value)} placeholder="https://github.com/org/app" />
          </label>
          <p className="muted">You can also bind this later from the board header. A column Agent can use a different folder if needed.</p>
        </details>
        <button type="submit" className="btn btn-primary" disabled={!boardName || createBoard.isPending}>
          {createBoard.isPending ? 'Creating…' : 'Create board'}
        </button>
      </form>

      <ConnectorHealth />
    </div>
  );
}
