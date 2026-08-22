import { FormEvent, useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '../api/client';
import { STATUS_LABEL } from '../status';
import { BoardDetail, CardStatus, CardStatusMachine, Stage } from '../types';
import { AgentConfigModal } from './AgentConfig';
import { Dialog } from './Dialog';

interface Props {
  boardId: string;
}

function apiErrorMessage(error: unknown): string {
  if (!(error instanceof Error)) {
    return 'Request failed';
  }
  try {
    const parsed: unknown = JSON.parse(error.message);
    if (parsed && typeof parsed === 'object' && 'detail' in parsed && typeof parsed.detail === 'string') {
      return parsed.detail;
    }
  } catch {
    /* response was not JSON */
  }
  return error.message;
}

export function StateMachineEditor({ boardId }: Props) {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [agentStage, setAgentStage] = useState<Stage | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const { data: board, isLoading } = useQuery({
    queryKey: ['board', boardId],
    queryFn: () => apiClient.get<BoardDetail>(`/boards/${boardId}`)
  });

  const { data: cardMachine } = useQuery({
    queryKey: ['card-status-machine'],
    queryFn: () => apiClient.get<CardStatusMachine>('/orchestration/card-status')
  });

  const stages = useMemo(() => (board ? [...board.stages].sort((left, right) => left.order - right.order) : []), [board]);
  const selected = stages.find((stage) => stage.id === selectedId) ?? null;
  const cardsOnSelected = board?.cards.filter((card) => card.current_stage_id === selected?.id).length ?? 0;

  const invalidateBoard = () => {
    queryClient.invalidateQueries({ queryKey: ['board', boardId] });
    queryClient.invalidateQueries({ queryKey: ['boards'] });
  };

  const createStage = useMutation({
    mutationFn: async (name: string) =>
      apiClient.post<Stage>(`/boards/${boardId}/stages`, {
        name,
        require_approval: true
      }),
    onSuccess: (stage) => {
      invalidateBoard();
      setSelectedId(stage.id);
    }
  });

  const updateStage = useMutation({
    mutationFn: async (payload: { name?: string; require_approval?: boolean }) => apiClient.put<Stage>(`/stages/${selected?.id}`, payload),
    onSuccess: invalidateBoard
  });

  const reorderStages = useMutation({
    mutationFn: async (stageIds: string[]) => apiClient.put<Stage[]>(`/boards/${boardId}/stages/reorder`, { stage_ids: stageIds }),
    onSuccess: invalidateBoard
  });

  const deleteStage = useMutation({
    mutationFn: async () => apiClient.delete(`/stages/${selected?.id}`),
    onSuccess: () => {
      setConfirmDelete(false);
      setSelectedId(null);
      invalidateBoard();
    }
  });

  const moveSelected = (direction: -1 | 1) => {
    if (!selected) {
      return;
    }
    const index = stages.findIndex((stage) => stage.id === selected.id);
    const next = index + direction;
    if (next < 0 || next >= stages.length) {
      return;
    }
    const ids = stages.map((stage) => stage.id);
    [ids[index], ids[next]] = [ids[next], ids[index]];
    reorderStages.mutate(ids);
  };

  if (isLoading || !board) {
    return <div className="muted">Loading state machine…</div>;
  }

  const busy = createStage.isPending || updateStage.isPending || reorderStages.isPending || deleteStage.isPending;
  const error = createStage.error || updateStage.error || reorderStages.error || deleteStage.error;

  return (
    <div className="machine">
      <div className="board-head">
        <div>
          <h1>State machine · {board.name}</h1>
          <p>Stages are workflow states. Cards enter on the first stage and move right through a human gate or auto-advance.</p>
        </div>
      </div>

      {error ? <p className="error">{apiErrorMessage(error)}</p> : null}

      <div className="machine-layout">
        <section className="panel machine-canvas" aria-label="Workflow">
          <h2>Workflow</h2>
          <div className="machine-flow">
            <div className="machine-terminal">Start</div>
            <MachineEdge label="create" />
            {stages.map((stage, index) => (
              <div key={stage.id} className="machine-step">
                {index > 0 ? (
                  <MachineEdge label={stages[index - 1].require_approval ? 'Human gate' : 'Auto-advance'} gated={stages[index - 1].require_approval} />
                ) : null}
                <button
                  type="button"
                  className={`machine-node${stage.id === selectedId ? ' is-selected' : ''}${stage.require_approval ? ' is-gated' : ' is-auto'}`}
                  onClick={() => setSelectedId(stage.id)}
                  aria-pressed={stage.id === selectedId}
                >
                  <span className="machine-node-order">{index + 1}</span>
                  <strong>{stage.name}</strong>
                  <span>{stage.require_approval ? 'Human gate' : 'Auto-advance'}</span>
                </button>
              </div>
            ))}
            {stages.length ? (
              <MachineEdge
                label={stages[stages.length - 1].require_approval ? 'Human gate' : 'Auto-advance'}
                gated={stages[stages.length - 1].require_approval}
              />
            ) : null}
            <div className="machine-terminal is-done">Done</div>
          </div>
          <AddStageForm disabled={busy} pending={createStage.isPending} onAdd={(name) => createStage.mutate(name)} />
        </section>

        <aside className="panel machine-inspector">
          <h2>Stage</h2>
          {selected ? (
            <StageInspector
              stage={selected}
              cardCount={cardsOnSelected}
              isFirst={stages[0]?.id === selected.id}
              isLast={stages[stages.length - 1]?.id === selected.id}
              canDelete={stages.length > 1 && cardsOnSelected === 0}
              busy={busy}
              onSaveName={(name) => updateStage.mutate({ name })}
              onToggleGate={(requireApproval) => updateStage.mutate({ require_approval: requireApproval })}
              onMoveLeft={() => moveSelected(-1)}
              onMoveRight={() => moveSelected(1)}
              onEditAgent={() => setAgentStage(selected)}
              onDelete={() => setConfirmDelete(true)}
            />
          ) : (
            <p className="muted">Select a stage to rename it, toggle the gate, reorder, or edit its agent.</p>
          )}
        </aside>
      </div>

      <CardLifecycleLegend machine={cardMachine} />

      <AgentConfigModal stage={agentStage} onClose={() => setAgentStage(null)} />

      <Dialog open={confirmDelete && Boolean(selected)} onClose={() => setConfirmDelete(false)} labelledBy="delete-stage-title" variant="modal">
        <div className="modal-head">
          <h2 id="delete-stage-title">Delete stage</h2>
          <button type="button" className="btn btn-ghost" onClick={() => setConfirmDelete(false)}>
            Close
          </button>
        </div>
        <p>
          Remove <strong>{selected?.name}</strong> from this machine? Cards will keep using the remaining stages.
        </p>
        <div className="new-board">
          <button type="button" className="btn btn-danger" onClick={() => deleteStage.mutate()} disabled={deleteStage.isPending}>
            {deleteStage.isPending ? 'Deleting…' : 'Delete stage'}
          </button>
          <button type="button" className="btn btn-ghost" onClick={() => setConfirmDelete(false)}>
            Cancel
          </button>
        </div>
      </Dialog>
    </div>
  );
}

function MachineEdge({ label, gated = false }: { label: string; gated?: boolean }) {
  return (
    <div className={`machine-edge${gated ? ' is-gated' : ''}`} aria-hidden="true">
      <span>{label}</span>
      <span className="machine-arrow" />
    </div>
  );
}

function AddStageForm({ disabled, pending, onAdd }: { disabled: boolean; pending: boolean; onAdd: (name: string) => void }) {
  const [name, setName] = useState('');
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      return;
    }
    onAdd(trimmed);
    setName('');
  };
  return (
    <form className="machine-add" onSubmit={submit}>
      <label className="field">
        Add stage
        <input className="input" value={name} onChange={(event) => setName(event.target.value)} placeholder="Stage name" disabled={disabled} />
      </label>
      <button type="submit" className="btn btn-primary" disabled={disabled || !name.trim()}>
        {pending ? 'Adding…' : 'Add to machine'}
      </button>
    </form>
  );
}

interface InspectorProps {
  stage: Stage;
  cardCount: number;
  isFirst: boolean;
  isLast: boolean;
  canDelete: boolean;
  busy: boolean;
  onSaveName: (name: string) => void;
  onToggleGate: (requireApproval: boolean) => void;
  onMoveLeft: () => void;
  onMoveRight: () => void;
  onEditAgent: () => void;
  onDelete: () => void;
}

function StageInspector({
  stage,
  cardCount,
  isFirst,
  isLast,
  canDelete,
  busy,
  onSaveName,
  onToggleGate,
  onMoveLeft,
  onMoveRight,
  onEditAgent,
  onDelete
}: InspectorProps) {
  const [name, setName] = useState(stage.name);

  useEffect(() => {
    setName(stage.name);
  }, [stage.id, stage.name]);

  return (
    <form
      className="machine-inspector-form"
      onSubmit={(event) => {
        event.preventDefault();
        const trimmed = name.trim();
        if (trimmed && trimmed !== stage.name) {
          onSaveName(trimmed);
        }
      }}
    >
      <label className="field">
        Name
        <input className="input" name="stage-name" value={name} onChange={(event) => setName(event.target.value)} disabled={busy} />
      </label>
      <button type="submit" className="btn" disabled={busy || !name.trim() || name.trim() === stage.name}>
        Save name
      </button>

      <div className="field">
        <span>Progression</span>
        <label className="tool-row">
          <input type="checkbox" checked={stage.require_approval} disabled={busy} onChange={(event) => onToggleGate(event.target.checked)} />
          Require human approval
        </label>
      </div>

      <p className="muted">
        {cardCount} card{cardCount === 1 ? '' : 's'} on this stage. Agent model: {stage.agent_config?.model ?? 'unset'}.
      </p>

      <div className="machine-inspector-actions">
        <button type="button" className="btn" onClick={onMoveLeft} disabled={busy || isFirst}>
          Move left
        </button>
        <button type="button" className="btn" onClick={onMoveRight} disabled={busy || isLast}>
          Move right
        </button>
        <button type="button" className="btn" onClick={onEditAgent}>
          Edit agent
        </button>
        <button
          type="button"
          className="btn btn-danger"
          onClick={onDelete}
          disabled={busy || !canDelete}
          title={!canDelete ? 'Keep at least one stage, and move cards off this stage first' : undefined}
        >
          Delete
        </button>
      </div>
    </form>
  );
}

function CardLifecycleLegend({ machine }: { machine?: CardStatusMachine }) {
  const states = machine?.states ?? (['idle', 'running', 'waiting_approval', 'blocked', 'done'] satisfies CardStatus[]);
  const transitions = machine?.transitions;
  return (
    <section className="panel">
      <h2>Card lifecycle</h2>
      <p className="muted">Fixed per-card statuses inside a stage. This machine is not editable — gates and stage order are.</p>
      <div className="lifecycle-flow">
        {states.map((status) => {
          const next = transitions?.[status] ?? [];
          return (
            <div key={status} className="lifecycle-node">
              <span className={`status status-${status}`}>{STATUS_LABEL[status] ?? status}</span>
              {next.length ? (
                <span className="lifecycle-next">→ {next.map((target) => STATUS_LABEL[target] ?? target).join(', ')}</span>
              ) : (
                <span className="lifecycle-next">terminal</span>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
