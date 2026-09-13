import { FormEvent, useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '../api/client';
import { entryStageId, groupStages } from '../boardLayout';
import { BoardDetail, Card, Stage } from '../types';
import { repoChipLabel } from '../workspaceLabel';
import { AgentConfigModal } from './AgentConfig';
import { CardDrawer } from './CardDrawer';
import { CardHistory } from './CardHistory';
import { Column } from './Column';
import { Dialog } from './Dialog';

interface Props {
  boardId: string;
  onEditMachine?: () => void;
}

export function Board({ boardId, onEditMachine }: Props) {
  const [selectedCard, setSelectedCard] = useState<Card | null>(null);
  const [historyCard, setHistoryCard] = useState<Card | null>(null);
  const [selectedStage, setSelectedStage] = useState<Stage | null>(null);

  const { data: board, isLoading } = useQuery({
    queryKey: ['board', boardId],
    queryFn: () => apiClient.get<BoardDetail>(`/boards/${boardId}`),
    refetchInterval: (query) =>
      query.state.data?.cards.some((card) => card.status === 'running' || card.status === 'waiting_join' || card.status === 'waiting_tool_approval')
        ? 2000
        : false
  });

  const cardsByStage = useMemo(() => {
    const groups = new Map<string, Card[]>();
    board?.stages.forEach((stage) => groups.set(stage.id, []));
    board?.cards.forEach((card) => {
      if (card.current_stage_id && groups.has(card.current_stage_id)) {
        groups.get(card.current_stage_id)?.push(card);
      }
    });
    return groups;
  }, [board]);

  if (isLoading || !board) {
    return <div className="muted">Loading board…</div>;
  }

  const stages = [...board.stages].sort((left, right) => left.order - right.order || (left.lane ?? 0) - (right.lane ?? 0));
  const columns = groupStages(stages);
  const entryId = entryStageId(stages);
  const rowCount = Math.max(1, ...stages.map((stage) => (stage.lane ?? 0) + 1));
  const liveCard = selectedCard ? (board.cards.find((item) => item.id === selectedCard.id) ?? selectedCard) : null;
  const liveHistoryCard = historyCard ? (board.cards.find((item) => item.id === historyCard.id) ?? historyCard) : null;

  if (liveHistoryCard) {
    return (
      <CardHistory
        card={liveHistoryCard}
        board={board}
        onBack={() => setHistoryCard(null)}
        onOpenCard={() => {
          setSelectedCard(liveHistoryCard);
          setHistoryCard(null);
        }}
      />
    );
  }

  return (
    <div>
      <div className="board-head">
        <div>
          <h1>{board.name}</h1>
          <p>{board.description || 'Each column is a workflow step. Cards follow the lines you draw. Column and row only place stages on the board.'}</p>
        </div>
        <div className="board-head-actions">
          <BoardWorkspace board={board} />
          {onEditMachine ? (
            <button type="button" className="btn" onClick={onEditMachine}>
              Edit state machine
            </button>
          ) : null}
        </div>
      </div>

      <div
        className="board-grid"
        style={{
          gridTemplateColumns: `64px repeat(${columns.length}, minmax(280px, 1fr))`,
          gridTemplateRows: `28px repeat(${rowCount}, minmax(240px, 1fr))`
        }}
      >
        <div className="board-grid-corner" />
        {columns.map((group, columnIndex) => {
          const parallel = group.length > 1;
          return (
            <header
              key={`col-${group[0].id}`}
              className={`board-column-banner${parallel ? ' is-parallel' : ''}`}
              style={{ gridColumn: columnIndex + 2, gridRow: 1 }}
            >
              <span>Column {group[0].order}</span>
              {parallel ? <span className="board-column-parallel">{group.length} rows in parallel</span> : null}
            </header>
          );
        })}
        {Array.from({ length: rowCount }, (_, index) => (
          <div key={`row-${index}`} className="board-row-label" style={{ gridColumn: 1, gridRow: index + 2 }}>
            Row {index + 1}
          </div>
        ))}
        {columns.flatMap((group, columnIndex) => {
          const parallel = group.length > 1;
          return Array.from({ length: rowCount }, (_, index) => {
            const row = index + 1;
            const stage = group.find((item) => (item.lane ?? 0) + 1 === row);
            if (!stage) {
              return (
                <div
                  key={`${group[0].id}-empty-${row}`}
                  className={`board-empty-cell${parallel ? ' is-parallel' : ''}`}
                  style={{ gridColumn: columnIndex + 2, gridRow: row + 1 }}
                />
              );
            }
            return (
              <div key={stage.id} className={`board-cell${parallel ? ' is-parallel' : ''}`} style={{ gridColumn: columnIndex + 2, gridRow: row + 1 }}>
                <Column
                  boardId={boardId}
                  stage={stage}
                  cards={cardsByStage.get(stage.id) ?? []}
                  isFirst={stage.id === entryId}
                  row={row}
                  parallel={parallel}
                  openCardId={liveCard?.id ?? null}
                  onOpenCard={setSelectedCard}
                  onOpenConfig={setSelectedStage}
                />
              </div>
            );
          });
        })}
      </div>

      <CardDrawer
        card={liveCard}
        board={board}
        onClose={() => setSelectedCard(null)}
        onOpenHistory={
          liveCard
            ? () => {
                setHistoryCard(liveCard);
                setSelectedCard(null);
              }
            : undefined
        }
      />
      <AgentConfigModal
        stage={selectedStage}
        boardWorkspace={{ path: board.workspace_path ?? '', git_url: board.git_url ?? '' }}
        onClose={() => setSelectedStage(null)}
      />
    </div>
  );
}

function BoardWorkspace({ board }: { board: BoardDetail }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [path, setPath] = useState(board.workspace_path ?? '');
  const [gitUrl, setGitUrl] = useState(board.git_url ?? '');

  useEffect(() => {
    setPath(board.workspace_path ?? '');
    setGitUrl(board.git_url ?? '');
  }, [board.id, board.workspace_path, board.git_url]);

  const bound = Boolean(board.git_url || board.workspace_path);
  const label = repoChipLabel(board.workspace_path, board.git_url);

  const { data: detected } = useQuery({
    queryKey: ['workspace', board.id],
    enabled: open,
    queryFn: () =>
      apiClient.get<{ path?: string | null; git_url?: string | null; github_repo?: string | null; source?: string | null }>(
        `/workspace?board_id=${encodeURIComponent(board.id)}`
      )
  });

  const save = useMutation({
    mutationFn: async () => apiClient.put<BoardDetail>(`/boards/${board.id}`, { workspace_path: path, git_url: gitUrl }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['board', board.id] });
      queryClient.invalidateQueries({ queryKey: ['boards'] });
      queryClient.invalidateQueries({ queryKey: ['workspace', board.id] });
      setOpen(false);
    }
  });

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate();
  };

  const saveError = (() => {
    if (!save.isError || !save.error) {
      return null;
    }
    const raw = save.error instanceof Error ? save.error.message : String(save.error);
    try {
      const parsed = JSON.parse(raw) as { detail?: unknown };
      if (typeof parsed.detail === 'string' && parsed.detail.trim()) {
        return parsed.detail;
      }
    } catch {
      /* plain text */
    }
    return raw || 'Could not save the git repo.';
  })();

  return (
    <>
      <button
        type="button"
        className={`chip repo-chip${bound ? '' : ' is-empty'}`}
        onClick={() => setOpen(true)}
        title={bound ? `${board.workspace_path || ''} ${board.git_url || ''}`.trim() : 'Bind a git repo for this board'}
      >
        {bound ? label : 'Bind git repo'}
      </button>
      <Dialog open={open} onClose={() => setOpen(false)} labelledBy="board-workspace-title" variant="modal">
        <form className="workspace-bind" onSubmit={onSubmit}>
          <div className="modal-head">
            <h2 id="board-workspace-title">Git repo for this board</h2>
            <button type="button" className="btn btn-ghost" onClick={() => setOpen(false)}>
              Close
            </button>
          </div>
          <p className="muted">
            Agents on this board work in one folder. The folder must exist on this machine; the GitHub URL must look like a real git remote.
          </p>
          <label className="field">
            Folder on this machine
            <input className="input" value={path} onChange={(event) => setPath(event.target.value)} placeholder="/home/you/projects/app" autoComplete="off" />
          </label>
          <label className="field">
            GitHub or git URL
            <input
              className="input"
              value={gitUrl}
              onChange={(event) => setGitUrl(event.target.value)}
              placeholder="https://github.com/org/app"
              autoComplete="off"
            />
          </label>
          {detected?.path && detected.source === 'board' && bound ? (
            <p className="muted">Workspace API sees {detected.github_repo || detected.path} for this board.</p>
          ) : null}
          {detected?.path && !path && detected.source !== 'board' ? (
            <p className="muted">
              Norns is running from {detected.github_repo || detected.path}.{' '}
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => {
                  setPath(detected.path || '');
                  setGitUrl(detected.git_url || '');
                }}
              >
                Use this folder
              </button>
            </p>
          ) : null}
          {saveError ? <div className="error">{saveError}</div> : null}
          <div className="connector-actions">
            <button type="submit" className="btn btn-primary" disabled={save.isPending}>
              {save.isPending ? 'Saving…' : 'Save'}
            </button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
