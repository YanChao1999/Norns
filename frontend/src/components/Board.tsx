import { FormEvent, useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '../api/client';
import { entryStageId, groupStages } from '../boardLayout';
import { useI18n } from '../i18n';
import { boardHasParallel, softJoinProgress } from '../softJoin';
import { BoardDetail, Card, Stage } from '../types';
import { repoChipLabel } from '../workspaceLabel';
import { AgentConfigModal } from './AgentConfig';
import { CardDrawer } from './CardDrawer';
import { CardHistory } from './CardHistory';
import { Column } from './Column';
import { Dialog } from './Dialog';
import { SoftJoinBridge } from './SoftJoinBridge';

interface Props {
  boardId: string;
  onEditMachine?: () => void;
  practiceMode?: boolean;
}

export function Board({ boardId, onEditMachine, practiceMode = false }: Props) {
  const { t } = useI18n();
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
    return <div className="muted">{t('board.loading')}</div>;
  }

  const stages = [...board.stages].sort((left, right) => left.order - right.order || (left.lane ?? 0) - (right.lane ?? 0));
  const columns = groupStages(stages);
  const entryId = entryStageId(stages);
  const parallelMode = boardHasParallel(columns);
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
          <p>
            {board.description ||
              (practiceMode
                ? t('practice.body')
                : 'Each column is a workflow step. Cards follow the lines you draw.')}
          </p>
        </div>
        <div className="board-head-actions">
          <BoardWorkspace board={board} />
          {onEditMachine ? (
            <button type="button" className="btn" onClick={onEditMachine}>
              {t('board.editMachine')}
            </button>
          ) : null}
        </div>
      </div>

      {parallelMode ? (
        <StageRail
          boardId={boardId}
          board={board}
          columns={columns}
          cardsByStage={cardsByStage}
          entryId={entryId}
          openCardId={liveCard?.id ?? null}
          onOpenCard={setSelectedCard}
          onOpenConfig={setSelectedStage}
        />
      ) : (
        <div className="stage-rail-linear">
          {columns.map((group) => {
            const stage = group[0];
            return (
              <Column
                key={stage.id}
                boardId={boardId}
                stage={stage}
                cards={cardsByStage.get(stage.id) ?? []}
                isFirst={stage.id === entryId}
                openCardId={liveCard?.id ?? null}
                onOpenCard={setSelectedCard}
                onOpenConfig={setSelectedStage}
              />
            );
          })}
        </div>
      )}

      <CardDrawer
        card={liveCard}
        board={board}
        practiceMode={practiceMode}
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

function StageRail({
  boardId,
  board,
  columns,
  cardsByStage,
  entryId,
  openCardId,
  onOpenCard,
  onOpenConfig
}: {
  boardId: string;
  board: BoardDetail;
  columns: Stage[][];
  cardsByStage: Map<string, Card[]>;
  entryId?: string;
  openCardId: string | null;
  onOpenCard: (card: Card) => void;
  onOpenConfig: (stage: Stage) => void;
}) {
  const { t } = useI18n();
  const parallelIndex = columns.findIndex((group) => group.length > 1);
  const parallelGroup = parallelIndex >= 0 ? columns[parallelIndex] : null;
  const progress = parallelGroup ? softJoinProgress(parallelGroup, board.cards) : null;
  const joinLocked = Boolean(parallelGroup && progress && !progress.complete);

  return (
    <div className="stage-rail">
      {columns.map((group, index) => {
        if (group.length > 1) {
          const isLast = index === columns.length - 1;
          return (
            <div key={`parallel-${group[0].id}`} style={{ display: 'contents' }}>
              <div className="parallel-frame">
                <div className="parallel-frame-badge">{t('board.inParallel')}</div>
                <div className="parallel-lanes">
                  {[...group]
                    .sort((left, right) => (left.lane ?? 0) - (right.lane ?? 0))
                    .map((stage) => (
                      <Column
                        key={stage.id}
                        boardId={boardId}
                        stage={stage}
                        cards={cardsByStage.get(stage.id) ?? []}
                        isFirst={stage.id === entryId}
                        row={(stage.lane ?? 0) + 1}
                        parallel
                        compact
                        openCardId={openCardId}
                        onOpenCard={onOpenCard}
                        onOpenConfig={onOpenConfig}
                      />
                    ))}
                </div>
              </div>
              {isLast && progress ? <SoftJoinBridge progress={progress} onOpenCard={onOpenCard} /> : null}
            </div>
          );
        }

        const stage = group[0];
        const afterParallel = parallelIndex >= 0 && index === parallelIndex + 1;
        const terminalLocked = afterParallel && joinLocked && Boolean(stage.confirm_writes);

        return (
          <div key={stage.id} style={{ display: 'contents' }}>
            {afterParallel && progress ? <SoftJoinBridge progress={progress} onOpenCard={onOpenCard} /> : null}
            <Column
              boardId={boardId}
              stage={stage}
              cards={cardsByStage.get(stage.id) ?? []}
              isFirst={stage.id === entryId}
              locked={terminalLocked}
              openCardId={openCardId}
              onOpenCard={onOpenCard}
              onOpenConfig={onOpenConfig}
            />
          </div>
        );
      })}
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
    queryKey: ['workspace-detected'],
    enabled: open && !bound,
    queryFn: () => apiClient.get<{ path?: string | null; git_url?: string | null; github_repo?: string | null }>('/workspace')
  });

  const save = useMutation({
    mutationFn: async () => apiClient.put<BoardDetail>(`/boards/${board.id}`, { workspace_path: path, git_url: gitUrl }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['board', board.id] });
      queryClient.invalidateQueries({ queryKey: ['boards'] });
      setOpen(false);
    }
  });

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate();
  };

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
            Agents on this board work in one folder. Pick the project checkout; the GitHub URL is optional and fills in from origin when you leave it blank.
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
          {detected?.path && !path ? (
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
          {save.isError ? <div className="error">Could not save the git repo.</div> : null}
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
