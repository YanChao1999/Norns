import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { apiClient } from './api/client';
import { Board } from './components/Board';
import { LoginForm } from './components/LoginForm';
import { Settings } from './components/Settings';
import { StateMachineEditor } from './components/StateMachineEditor';
import { NO_API_KEY_HINT } from './runHints';
import { BoardDetail, BoardSummary } from './types';

type View = 'board' | 'machine' | 'settings';

export default function App() {
  const queryClient = useQueryClient();
  const [username, setUsername] = useState<string | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [selectedBoardId, setSelectedBoardId] = useState<string>('');
  const [view, setView] = useState<View>('board');

  useEffect(() => {
    let cancelled = false;
    apiClient
      .get<{ username: string }>('/auth/me')
      .then((user) => {
        if (!cancelled) {
          setUsername(user.username);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setUsername(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setAuthChecked(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const { data: runtime } = useQuery({
    queryKey: ['health'],
    enabled: Boolean(username),
    queryFn: () => apiClient.get<{ status: string; openai_configured?: boolean }>('/health')
  });

  const { data: boards = [], isLoading } = useQuery({
    queryKey: ['boards'],
    enabled: Boolean(username),
    queryFn: () => apiClient.get<BoardSummary[]>('/boards')
  });

  const { data: selectedBoard } = useQuery({
    queryKey: ['board', selectedBoardId],
    enabled: Boolean(username && selectedBoardId),
    queryFn: () => apiClient.get<BoardDetail>(`/boards/${selectedBoardId}`),
    refetchInterval: (query) => (query.state.data?.cards.some((card) => card.status === 'running') ? 2000 : false)
  });

  useEffect(() => {
    if (!selectedBoardId && boards.length) {
      setSelectedBoardId(boards[0].id);
    }
  }, [boards, selectedBoardId]);

  const handleLogout = async () => {
    await apiClient.post('/auth/logout');
    queryClient.clear();
    setSelectedBoardId('');
    setUsername(null);
    setView('board');
  };

  if (!authChecked) {
    return <div className="app-boot">Checking session</div>;
  }

  if (!username) {
    return <LoginForm onLoggedIn={setUsername} />;
  }

  const waitingCount =
    selectedBoard?.cards.filter((card) => card.status === 'waiting_approval' || card.status === 'waiting_tool_approval').length ?? 0;

  return (
    <div>
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">Norns</span>
          <span className="brand-sub">Control room</span>
        </div>
        <nav className="board-switcher" aria-label="Boards">
          {boards.map((board) => (
            <button
              key={board.id}
              type="button"
              className={`chip${board.id === selectedBoardId && view !== 'settings' ? ' is-active' : ''}`}
              onClick={() => {
                setSelectedBoardId(board.id);
                setView('board');
              }}
            >
              {board.name}
            </button>
          ))}
        </nav>
        <div className="topbar-meta">
          <span className={`wait-count${waitingCount ? '' : ' is-clear'}`}>{waitingCount} waiting</span>
          <button type="button" className={`chip${view === 'machine' ? ' is-active' : ''}`} onClick={() => setView('machine')} disabled={!selectedBoardId}>
            Machine
          </button>
          <button type="button" className={`chip${view === 'settings' ? ' is-active' : ''}`} onClick={() => setView('settings')}>
            Settings
          </button>
          <span className="user-name">{username}</span>
          <button type="button" className="btn btn-ghost" onClick={handleLogout}>
            Log out
          </button>
        </div>
      </header>

      <main className="workspace">
        {runtime?.openai_configured === false ? (
          <p className="notice" role="status">
            {NO_API_KEY_HINT}
          </p>
        ) : null}
        {view === 'settings' ? (
          <Settings
            onCreated={(boardId) => {
              setSelectedBoardId(boardId);
              setView('board');
            }}
          />
        ) : view === 'machine' ? (
          selectedBoardId ? (
            <StateMachineEditor boardId={selectedBoardId} />
          ) : (
            <div className="empty-board">Create a board in Settings before editing the state machine.</div>
          )
        ) : (
          <>
            {isLoading ? <div className="muted">Loading boards…</div> : null}
            {!boards.length && !isLoading ? <div className="empty-board">Create a board in Settings to start orchestration.</div> : null}
            {selectedBoardId ? <Board boardId={selectedBoardId} onEditMachine={() => setView('machine')} /> : null}
          </>
        )}
      </main>
    </div>
  );
}
