import { useEffect, useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { apiClient } from './api/client';
import { Board } from './components/Board';
import { LoginForm } from './components/LoginForm';
import { PracticeBanner, PracticeCard } from './components/PracticeBanner';
import { Settings } from './components/Settings';
import { StateMachineEditor } from './components/StateMachineEditor';
import { useI18n } from './i18n';
import { boardHasParallel } from './softJoin';
import { groupStages } from './boardLayout';
import { applyTheme, readTheme, ThemeId } from './theme';
import { BoardDetail, BoardSummary } from './types';

type View = 'board' | 'machine' | 'settings';

export default function App() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [username, setUsername] = useState<string | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [selectedBoardId, setSelectedBoardId] = useState<string>('');
  const [view, setView] = useState<View>('board');
  const [theme, setTheme] = useState<ThemeId>(() => readTheme());
  const [practiceDismissed, setPracticeDismissed] = useState(false);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

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
    queryFn: () => apiClient.get<{ status: string; llm_configured?: boolean; openai_configured?: boolean }>('/health')
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

  const llmConfigured = runtime == null ? null : Boolean(runtime.llm_configured ?? runtime.openai_configured);
  const showPractice = llmConfigured === false && !practiceDismissed;

  const waitingCount =
    selectedBoard?.cards.filter((card) => card.status === 'waiting_approval' || card.status === 'waiting_tool_approval').length ?? 0;
  const pullingCount = selectedBoard?.cards.filter((card) => card.status === 'running').length ?? 0;
  const hasParallel = useMemo(
    () => (selectedBoard ? boardHasParallel(groupStages(selectedBoard.stages)) : false),
    [selectedBoard]
  );

  if (!authChecked) {
    return <div className="app-boot">{t('app.checkingSession')}</div>;
  }

  if (!username) {
    return <LoginForm onLoggedIn={setUsername} />;
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">{t('app.brand')}</span>
          <span className="brand-divider" aria-hidden="true" />
          <span className="brand-sub">
            {t('app.controlRoom')}
            {selectedBoard && view !== 'settings' ? ` · ${selectedBoard.name}` : ''}
          </span>
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
          <div className="theme-mark" title={t('app.themeMark')}>
            <span className="theme-mark-icon" aria-hidden="true">
              ···
            </span>
            <span>{t('app.themeMark')}</span>
          </div>
          <button type="button" className={`chip${view === 'machine' ? ' is-active' : ''}`} onClick={() => setView('machine')} disabled={!selectedBoardId}>
            {t('app.machine')}
          </button>
          <button type="button" className={`chip${view === 'settings' ? ' is-active' : ''}`} onClick={() => setView('settings')}>
            {t('app.settings')}
          </button>
          <span className="user-name">{username}</span>
          <button type="button" className="btn btn-ghost" onClick={handleLogout}>
            {t('app.logOut')}
          </button>
        </div>
        <div className="status-pills" aria-live="polite">
          <span className="status-pill is-waiting">{t('status.awaitingConfirm', { count: waitingCount })}</span>
          <span className="status-pill is-running">{t('status.inProgress', { count: pullingCount })}</span>
        </div>
      </header>

      <main className="workspace">
        {showPractice && view === 'board' ? (
          <PracticeBanner
            onGoSettings={() => setView('settings')}
            onContinue={() => setPracticeDismissed(true)}
          />
        ) : null}
        {view === 'settings' ? (
          <Settings
            board={selectedBoard}
            theme={theme}
            onThemeChange={setTheme}
            onCreated={(boardId) => {
              setSelectedBoardId(boardId);
              setView('board');
            }}
          />
        ) : view === 'machine' ? (
          selectedBoardId ? (
            <StateMachineEditor boardId={selectedBoardId} />
          ) : (
            <div className="empty-board">{t('app.emptyMachine')}</div>
          )
        ) : (
          <>
            {isLoading ? <div className="muted">{t('app.loadingBoards')}</div> : null}
            {!boards.length && !isLoading ? <div className="empty-board">{t('app.emptyBoard')}</div> : null}
            {selectedBoardId ? (
              <Board
                boardId={selectedBoardId}
                onEditMachine={() => setView('machine')}
                practiceMode={llmConfigured === false}
              />
            ) : null}
            {llmConfigured === false && view === 'board' ? <PracticeCard /> : null}
          </>
        )}
        <footer className="app-footer">
          <span>{hasParallel ? t('app.footerParallel') : `${t('app.brand')} ${t('app.controlRoom')}`}</span>
          <span>{llmConfigured === false ? t('app.footerPractice') : t('app.themeMark')}</span>
        </footer>
      </main>
    </div>
  );
}
