import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiClient } from './api/client';
import { Board } from './components/Board';
import { ConnectorHealth } from './components/ConnectorHealth';
import { BoardSummary } from './types';

async function ensureLogin() {
  try {
    await apiClient.get('/auth/me');
  } catch {
    await apiClient.post('/auth/login', { username: 'admin', password: 'admin' });
  }
}

export default function App() {
  const queryClient = useQueryClient();
  const [selectedBoardId, setSelectedBoardId] = useState<string>('');
  const [boardName, setBoardName] = useState('Default board');

  const { data: boards = [], isLoading } = useQuery({
    queryKey: ['boards'],
    queryFn: async () => {
      await ensureLogin();
      return apiClient.get<BoardSummary[]>('/boards');
    }
  });

  const createBoard = useMutation({
    mutationFn: async () =>
      apiClient.post<BoardSummary>('/boards', {
        name: boardName,
        description: 'Initial Norns board'
      }),
    onSuccess: (board) => {
      queryClient.invalidateQueries({ queryKey: ['boards'] });
      setSelectedBoardId(board.id);
    }
  });

  useEffect(() => {
    if (!selectedBoardId && boards.length) {
      setSelectedBoardId(boards[0].id);
    }
  }, [boards, selectedBoardId]);

  return (
    <div style={{ minHeight: '100vh', background: '#f1f5f9', color: '#0f172a' }}>
      <div style={{ maxWidth: 1400, margin: '0 auto', padding: 24, display: 'grid', gap: 16 }}>
        <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h1 style={{ marginBottom: 4 }}>Norns</h1>
            <p style={{ margin: 0, color: '#475569' }}>Approval-gated multi-agent Kanban orchestration.</p>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <input value={boardName} onChange={(event) => setBoardName(event.target.value)} placeholder="New board name" />
            <button onClick={() => createBoard.mutate()} disabled={!boardName || createBoard.isPending}>
              {createBoard.isPending ? 'Creating…' : 'Create board'}
            </button>
          </div>
        </header>

        <section style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {boards.map((board) => (
            <button
              key={board.id}
              onClick={() => setSelectedBoardId(board.id)}
              style={{
                padding: '8px 12px',
                borderRadius: 999,
                border: board.id === selectedBoardId ? '2px solid #2563eb' : '1px solid #cbd5e1',
                background: 'white'
              }}
            >
              {board.name}
            </button>
          ))}
        </section>

        <ConnectorHealth />

        {isLoading ? <div>Loading boards…</div> : null}
        {!boards.length && !isLoading ? <div>Create your first board to start orchestration.</div> : null}
        {selectedBoardId ? <Board boardId={selectedBoardId} /> : null}
      </div>
    </div>
  );
}
