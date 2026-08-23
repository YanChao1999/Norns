import { FormEvent, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '../api/client';
import { STATUS_LABEL } from '../status';
import { BoardDetail, CardStatus, CardStatusMachine, Stage, StageTransition } from '../types';
import { AgentConfigModal } from './AgentConfig';
import { Dialog } from './Dialog';

const DONE_ID = '__done__';

interface Props {
  boardId: string;
}

interface NodeBox {
  x: number;
  y: number;
  width: number;
  height: number;
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

function stageName(stages: Stage[], stageId: string | null): string {
  if (!stageId) {
    return 'Done';
  }
  return stages.find((stage) => stage.id === stageId)?.name ?? 'stage';
}

function lineCaption(edge: StageTransition, stages: Stage[]): string {
  const target = stageName(stages, edge.to_stage_id);
  const when = edge.event;
  if (!edge.condition_key.trim()) {
    return `${when} → ${target}`;
  }
  const clause =
    edge.condition_op === 'exists'
      ? `if ${edge.condition_key} exists`
      : `if ${edge.condition_key} ${edge.condition_op} ${edge.condition_value}`;
  return `${when} · ${clause} → ${target}`;
}

export function StateMachineEditor({ boardId }: Props) {
  const queryClient = useQueryClient();
  const graphRef = useRef<HTMLDivElement | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedLineId, setSelectedLineId] = useState<string | null>(null);
  const [drawingFrom, setDrawingFrom] = useState<string | null>(null);
  const [agentStage, setAgentStage] = useState<Stage | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [boxes, setBoxes] = useState<Record<string, NodeBox>>({});

  const { data: board, isLoading } = useQuery({
    queryKey: ['board', boardId],
    queryFn: () => apiClient.get<BoardDetail>(`/boards/${boardId}`)
  });

  const { data: cardMachine } = useQuery({
    queryKey: ['card-status-machine'],
    queryFn: () => apiClient.get<CardStatusMachine>('/orchestration/card-status')
  });

  const stages = useMemo(() => (board ? [...board.stages].sort((left, right) => left.order - right.order) : []), [board]);
  const lines = board?.transitions ?? [];
  const selected = stages.find((stage) => stage.id === selectedId) ?? null;
  const selectedLine = lines.find((edge) => edge.id === selectedLineId) ?? null;
  const cardsOnSelected = board?.cards.filter((card) => card.current_stage_id === selected?.id).length ?? 0;

  const measure = () => {
    const root = graphRef.current;
    if (!root) {
      return;
    }
    const origin = root.getBoundingClientRect();
    const next: Record<string, NodeBox> = {};
    root.querySelectorAll<HTMLElement>('[data-node]').forEach((node) => {
      const id = node.dataset.node;
      if (!id) {
        return;
      }
      const rect = node.getBoundingClientRect();
      next[id] = {
        x: rect.left - origin.left + rect.width / 2,
        y: rect.top - origin.top + rect.height / 2,
        width: rect.width,
        height: rect.height
      };
    });
    setBoxes(next);
  };

  useLayoutEffect(() => {
    measure();
    const root = graphRef.current;
    if (!root || typeof ResizeObserver === 'undefined') {
      return;
    }
    const observer = new ResizeObserver(() => measure());
    observer.observe(root);
    return () => observer.disconnect();
  }, [stages, lines.length, drawingFrom]);

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
      setSelectedLineId(null);
    }
  });

  const updateStage = useMutation({
    mutationFn: async (payload: { name?: string; require_approval?: boolean }) => apiClient.put<Stage>(`/stages/${selected?.id}`, payload),
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

  const createLine = useMutation({
    mutationFn: async (payload: { from_stage_id: string; to_stage_id: string | null; event: StageTransition['event'] }) =>
      apiClient.post<StageTransition>(`/boards/${boardId}/transitions`, payload),
    onSuccess: (edge) => {
      invalidateBoard();
      setDrawingFrom(null);
      setSelectedLineId(edge.id);
      setSelectedId(null);
    }
  });

  const updateLine = useMutation({
    mutationFn: async (payload: Partial<StageTransition>) => apiClient.put<StageTransition>(`/transitions/${selectedLine?.id}`, payload),
    onSuccess: invalidateBoard
  });

  const deleteLine = useMutation({
    mutationFn: async () => apiClient.delete(`/transitions/${selectedLine?.id}`),
    onSuccess: () => {
      setSelectedLineId(null);
      invalidateBoard();
    }
  });

  const pickNode = (nodeId: string) => {
    if (drawingFrom) {
      if (nodeId === drawingFrom) {
        setDrawingFrom(null);
        return;
      }
      createLine.mutate({
        from_stage_id: drawingFrom,
        to_stage_id: nodeId === DONE_ID ? null : nodeId,
        event: 'approve'
      });
      return;
    }
    if (nodeId === DONE_ID) {
      return;
    }
    setSelectedId(nodeId);
    setSelectedLineId(null);
  };

  if (isLoading || !board) {
    return <div className="muted">Loading state machine…</div>;
  }

  const busy =
    createStage.isPending ||
    updateStage.isPending ||
    deleteStage.isPending ||
    createLine.isPending ||
    updateLine.isPending ||
    deleteLine.isPending;
  const error = createStage.error || updateStage.error || deleteStage.error || createLine.error || updateLine.error || deleteLine.error;

  return (
    <div className="machine">
      <div className="board-head">
        <div>
          <h1>State machine · {board.name}</h1>
          <p>Draw lines between stages. Lines can go forward, back, or to Done. Add an If on a line to branch.</p>
        </div>
      </div>

      {error ? <p className="error">{apiErrorMessage(error)}</p> : null}

      <div className="machine-layout">
        <section className="panel machine-canvas" aria-label="Workflow">
          <div className="machine-toolbar">
            <h2>Workflow lines</h2>
            <button
              type="button"
              className={`btn${drawingFrom ? ' btn-primary' : ''}`}
              onClick={() => {
                setDrawingFrom(selectedId);
                setSelectedLineId(null);
              }}
              disabled={!selectedId && !drawingFrom}
            >
              {drawingFrom ? 'Click a target stage or Done' : 'Draw line from selected stage'}
            </button>
          </div>
          <div ref={graphRef} className={`machine-graph${drawingFrom ? ' is-drawing' : ''}`}>
            <svg className="machine-lines" aria-hidden="true">
              {lines.map((edge, index) => {
                const start = boxes[edge.from_stage_id];
                const end = boxes[edge.to_stage_id ?? DONE_ID];
                if (!start || !end) {
                  return null;
                }
                const backward = (end.x || 0) <= (start.x || 0);
                const lift = backward ? 36 + (index % 3) * 14 : 0;
                const path = backward
                  ? `M ${start.x} ${start.y} C ${start.x} ${start.y + lift}, ${end.x} ${end.y + lift}, ${end.x} ${end.y}`
                  : `M ${start.x} ${start.y} C ${(start.x + end.x) / 2} ${start.y}, ${(start.x + end.x) / 2} ${end.y}, ${end.x} ${end.y}`;
                return (
                  <g key={edge.id}>
                    <path
                      d={path}
                      className={`machine-line-hit${edge.id === selectedLineId ? ' is-selected' : ''}${edge.event === 'reject' ? ' is-reject' : ''}`}
                      onClick={(event) => {
                        event.stopPropagation();
                        setSelectedLineId(edge.id);
                        setSelectedId(null);
                        setDrawingFrom(null);
                      }}
                    />
                    <path
                      d={path}
                      className={
                        'machine-line' +
                        (edge.id === selectedLineId ? ' is-selected' : '') +
                        (edge.event === 'reject' ? ' is-reject' : '') +
                        (edge.condition_key ? ' is-if' : '')
                      }
                    />
                  </g>
                );
              })}
            </svg>
            <div className="machine-flow">
              <div className="machine-terminal">Start</div>
              {stages.map((stage, index) => (
                <button
                  key={stage.id}
                  type="button"
                  data-node={stage.id}
                  className={
                    'machine-node' +
                    (stage.id === selectedId ? ' is-selected' : '') +
                    (stage.id === drawingFrom ? ' is-drawing' : '') +
                    (stage.require_approval ? ' is-gated' : ' is-auto')
                  }
                  onClick={() => pickNode(stage.id)}
                  aria-pressed={stage.id === selectedId}
                >
                  <span className="machine-node-order">{index + 1}</span>
                  <strong>{stage.name}</strong>
                  <span>{stage.require_approval ? 'Human gate' : 'Auto-advance'}</span>
                </button>
              ))}
              <button type="button" data-node={DONE_ID} className="machine-terminal is-done" onClick={() => pickNode(DONE_ID)}>
                Done
              </button>
            </div>
          </div>
          <AddStageForm disabled={busy} pending={createStage.isPending} onAdd={(name) => createStage.mutate(name)} />
        </section>

        <aside className="panel machine-inspector">
          {selectedLine ? (
            <LineInspector
              edge={selectedLine}
              stages={stages}
              busy={busy}
              onSave={(payload) => updateLine.mutate(payload)}
              onDelete={() => deleteLine.mutate()}
            />
          ) : selected ? (
            <StageInspector
              stage={selected}
              stages={stages}
              cardCount={cardsOnSelected}
              canDelete={stages.length > 1 && cardsOnSelected === 0}
              busy={busy}
              outgoing={lines.filter((edge) => edge.from_stage_id === selected.id)}
              onSaveName={(name) => updateStage.mutate({ name })}
              onToggleGate={(requireApproval) => updateStage.mutate({ require_approval: requireApproval })}
              onDrawLine={() => {
                setDrawingFrom(selected.id);
                setSelectedLineId(null);
              }}
              onEditAgent={() => setAgentStage(selected)}
              onDelete={() => setConfirmDelete(true)}
              onSelectLine={(id) => {
                setSelectedLineId(id);
                setSelectedId(null);
              }}
            />
          ) : (
            <p className="muted">Select a stage, then Draw line and click another stage (including an earlier one) or Done.</p>
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
          Remove <strong>{selected?.name}</strong> from this machine? Outgoing and incoming lines are deleted with it.
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

interface StageInspectorProps {
  stage: Stage;
  stages: Stage[];
  cardCount: number;
  canDelete: boolean;
  busy: boolean;
  outgoing: StageTransition[];
  onSaveName: (name: string) => void;
  onToggleGate: (requireApproval: boolean) => void;
  onDrawLine: () => void;
  onEditAgent: () => void;
  onDelete: () => void;
  onSelectLine: (id: string) => void;
}

function StageInspector({
  stage,
  stages,
  cardCount,
  canDelete,
  busy,
  outgoing,
  onSaveName,
  onToggleGate,
  onDrawLine,
  onEditAgent,
  onDelete,
  onSelectLine
}: StageInspectorProps) {
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
      <h2>Stage</h2>
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
        <p className="muted">The agent may recommend approve or reject. The card still waits here until a human confirms.</p>
      </div>
      <p className="muted">
        {cardCount} card{cardCount === 1 ? '' : 's'} on this stage. Agent model: {stage.agent_config?.model ?? 'unset'}.
      </p>
      <div className="field">
        <span>Lines from this stage</span>
        {outgoing.length ? (
          <ul className="machine-line-list">
            {outgoing.map((edge) => (
              <li key={edge.id}>
                <button type="button" className="btn btn-ghost" onClick={() => onSelectLine(edge.id)}>
                  {lineCaption(edge, stages)}
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">No lines yet.</p>
        )}
      </div>
      <div className="machine-inspector-actions">
        <button type="button" className="btn btn-primary" onClick={onDrawLine} disabled={busy}>
          Draw line
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

function LineInspector({
  edge,
  stages,
  busy,
  onSave,
  onDelete
}: {
  edge: StageTransition;
  stages: Stage[];
  busy: boolean;
  onSave: (payload: Partial<StageTransition>) => void;
  onDelete: () => void;
}) {
  const [event, setEvent] = useState(edge.event);
  const [toId, setToId] = useState(edge.to_stage_id ?? DONE_ID);
  const [key, setKey] = useState(edge.condition_key);
  const [op, setOp] = useState(edge.condition_op);
  const [value, setValue] = useState(edge.condition_value);

  useEffect(() => {
    setEvent(edge.event);
    setToId(edge.to_stage_id ?? DONE_ID);
    setKey(edge.condition_key);
    setOp(edge.condition_op);
    setValue(edge.condition_value);
  }, [edge]);

  return (
    <form
      className="machine-inspector-form"
      onSubmit={(eventSubmit) => {
        eventSubmit.preventDefault();
        onSave({
          event,
          to_stage_id: toId === DONE_ID ? null : toId,
          condition_key: key.trim(),
          condition_op: op,
          condition_value: value
        });
      }}
    >
      <h2>Line</h2>
      <p className="muted">
        {stageName(stages, edge.from_stage_id)} → {stageName(stages, edge.to_stage_id)}
      </p>
      <label className="field">
        When
        <select className="select" value={event} onChange={(change) => setEvent(change.target.value as StageTransition['event'])} disabled={busy}>
          <option value="approve">Approve</option>
          <option value="reject">Reject (can go back)</option>
          <option value="auto">Auto-advance</option>
        </select>
      </label>
      <label className="field">
        To stage
        <select className="select" value={toId} onChange={(change) => setToId(change.target.value)} disabled={busy}>
          {stages.map((stage) => (
            <option key={stage.id} value={stage.id}>
              {stage.name}
              {stage.id === edge.from_stage_id ? ' (same stage)' : ''}
            </option>
          ))}
          <option value={DONE_ID}>Done</option>
        </select>
      </label>
      <label className="field">
        If (handoff field, optional)
        <input
          className="input"
          value={key}
          onChange={(change) => setKey(change.target.value)}
          placeholder="recommendation or risk"
          disabled={busy}
        />
      </label>
      <label className="field">
        Operator
        <select className="select" value={op} onChange={(change) => setOp(change.target.value as StageTransition['condition_op'])} disabled={busy}>
          <option value="eq">equals</option>
          <option value="contains">contains</option>
          <option value="exists">exists</option>
        </select>
      </label>
      <label className="field">
        Value
        <input className="input" value={value} onChange={(change) => setValue(change.target.value)} placeholder="high" disabled={busy || op === 'exists'} />
      </label>
      <p className="muted">
        Empty If is the default line. Conditional lines are checked first. Use If <code>recommendation</code> equals{' '}
        <code>approve</code> or <code>reject</code> to branch on the agent&apos;s suggestion after a human confirms.
      </p>
      <div className="machine-inspector-actions">
        <button type="submit" className="btn btn-primary" disabled={busy}>
          Save line
        </button>
        <button type="button" className="btn btn-danger" onClick={onDelete} disabled={busy}>
          Delete line
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
      <p className="muted">Fixed per-card statuses inside a stage. Workflow routing is the lines above.</p>
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
