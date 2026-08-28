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

interface Point {
  x: number;
  y: number;
}

function boxCenter(box: NodeBox): Point {
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

function clampShift(shift: number, size: number): number {
  const room = Math.max(0, size / 2 - 10);
  return Math.max(-room, Math.min(room, shift));
}

function anchor(box: NodeBox, side: 'left' | 'right' | 'top' | 'bottom', shift = 0): Point {
  const mid = boxCenter(box);
  const sideGap = 2;
  const endGap = 2;
  if (side === 'left') {
    return { x: box.x - sideGap, y: mid.y + clampShift(shift, box.height) };
  }
  if (side === 'right') {
    return { x: box.x + box.width + sideGap, y: mid.y + clampShift(shift, box.height) };
  }
  if (side === 'top') {
    return { x: mid.x + clampShift(shift, box.width), y: box.y - endGap };
  }
  return { x: mid.x + clampShift(shift, box.width), y: box.y + box.height + endGap };
}

function gapBetween(from: NodeBox, to: NodeBox): number {
  return Math.abs(boxCenter(to).x - boxCenter(from).x) - (from.width + to.width) / 2;
}

function cubic(start: Point, controlA: Point, controlB: Point, end: Point): string {
  return `M ${start.x} ${start.y} C ${controlA.x} ${controlA.y}, ${controlB.x} ${controlB.y}, ${end.x} ${end.y}`;
}

function elbow(start: Point, end: Point, railY: number): string {
  const radius = 10;
  const down = railY > start.y;
  const sign = down ? 1 : -1;
  const r = Math.min(radius, Math.abs(railY - start.y) / 2, Math.abs(end.x - start.x) / 2);
  const midStart = start.y + sign * r;
  const midEnd = end.y + sign * r;
  const goingLeft = end.x < start.x;
  const cornerStartX = start.x + (goingLeft ? -r : r);
  const cornerEndX = end.x + (goingLeft ? r : -r);
  return (
    `M ${start.x} ${start.y} L ${start.x} ${midStart} ` +
    `Q ${start.x} ${railY} ${cornerStartX} ${railY} ` +
    `L ${cornerEndX} ${railY} ` +
    `Q ${end.x} ${railY} ${end.x} ${midEnd} ` +
    `L ${end.x} ${end.y}`
  );
}

function linePath(from: NodeBox, to: NodeBox, self: boolean, slot: number): string {
  if (self) {
    const start = anchor(from, 'bottom', 14);
    const end = anchor(from, 'bottom', -14);
    const railY = start.y + 34 + slot * 14;
    return elbow(start, end, railY);
  }

  const goingRight = boxCenter(to).x >= boxCenter(from).x;
  const near = gapBetween(from, to) < 88;

  if (goingRight && near) {
    const shift = slot * 10;
    const start = anchor(from, 'right', shift);
    const end = anchor(to, 'left', shift);
    const midX = (start.x + end.x) / 2;
    return cubic(start, { x: midX, y: start.y }, { x: midX, y: end.y }, end);
  }

  if (goingRight) {
    const start = anchor(from, 'top', slot * 12);
    const end = anchor(to, 'top', slot * 12);
    const railY = Math.min(start.y, end.y) - 36 - slot * 14;
    return elbow(start, end, railY);
  }

  const start = anchor(from, 'bottom', 10 + slot * 12);
  const end = anchor(to, 'bottom', -10 - slot * 12);
  const railY = Math.max(start.y, end.y) + 36 + slot * 14;
  return elbow(start, end, railY);
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
  const clause = edge.condition_op === 'exists' ? `if ${edge.condition_key} exists` : `if ${edge.condition_key} ${edge.condition_op} ${edge.condition_value}`;
  return `${when} · ${clause} → ${target}`;
}

function stageRow(stage: Stage): number {
  return (stage.lane ?? 0) + 1;
}

function freeLane(stages: Stage[], order: number, preferred: number, selfId: string): number {
  const taken = new Set(stages.filter((stage) => stage.id !== selfId && stage.order === order).map((stage) => stage.lane ?? 0));
  let lane = Math.max(0, preferred);
  while (taken.has(lane)) {
    lane += 1;
  }
  return lane;
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

  const stages = useMemo(
    () => (board ? [...board.stages].sort((left, right) => left.order - right.order || (left.lane ?? 0) - (right.lane ?? 0)) : []),
    [board]
  );
  const columnRanks = useMemo(() => [...new Set(stages.map((stage) => stage.order))], [stages]);
  const rowCount = useMemo(() => Math.max(1, ...stages.map((stage) => stageRow(stage))), [stages]);
  const parallelColumns = useMemo(() => {
    const counts = new Map<number, number>();
    for (const stage of stages) {
      counts.set(stage.order, (counts.get(stage.order) ?? 0) + 1);
    }
    return new Set([...counts.entries()].filter(([, count]) => count > 1).map(([order]) => order));
  }, [stages]);
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
        x: rect.left - origin.left,
        y: rect.top - origin.top,
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
    mutationFn: async (payload: { name: string; parallel?: boolean; from_stage_id?: string }) =>
      apiClient.post<Stage>(`/boards/${boardId}/stages`, {
        name: payload.name,
        require_approval: true,
        parallel: payload.parallel,
        from_stage_id: payload.from_stage_id
      }),
    onSuccess: (stage) => {
      invalidateBoard();
      setSelectedId(stage.id);
      setSelectedLineId(null);
    }
  });

  const updateStage = useMutation({
    mutationFn: async (payload: { name?: string; require_approval?: boolean; confirm_writes?: boolean; order?: number; lane?: number }) =>
      apiClient.put<Stage>(`/stages/${selected?.id}`, payload),
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

  const busy = createStage.isPending || updateStage.isPending || deleteStage.isPending || createLine.isPending || updateLine.isPending || deleteLine.isPending;
  const error = createStage.error || updateStage.error || deleteStage.error || createLine.error || updateLine.error || deleteLine.error;

  return (
    <div className="machine">
      <div className="board-head">
        <div>
          <h1>State machine · {board.name}</h1>
          <p>Draw lines to split, join, or go back. Column and row only place stages. Parallel work needs two default lines from the same stage.</p>
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
              <defs>
                <marker id="machine-arrow" markerWidth="8" markerHeight="8" refX="8" refY="4" orient="auto">
                  <path d="M 0 0 L 8 4 L 0 8 z" fill="var(--accent)" />
                </marker>
                <marker id="machine-arrow-reject" markerWidth="8" markerHeight="8" refX="8" refY="4" orient="auto">
                  <path d="M 0 0 L 8 4 L 0 8 z" fill="var(--blocked)" />
                </marker>
              </defs>
              {lines.map((edge) => {
                const start = boxes[edge.from_stage_id];
                const end = boxes[edge.to_stage_id ?? DONE_ID];
                if (!start || !end) {
                  return null;
                }
                const slot = lines
                  .filter((other) => other.from_stage_id === edge.from_stage_id && other.to_stage_id === edge.to_stage_id)
                  .findIndex((other) => other.id === edge.id);
                const path = linePath(start, end, edge.from_stage_id === edge.to_stage_id, Math.max(0, slot));
                const reject = edge.event === 'reject';
                return (
                  <g key={edge.id}>
                    <path
                      d={path}
                      className={`machine-line-hit${edge.id === selectedLineId ? ' is-selected' : ''}${reject ? ' is-reject' : ''}`}
                      onClick={(click) => {
                        click.stopPropagation();
                        setSelectedLineId(edge.id);
                        setSelectedId(null);
                        setDrawingFrom(null);
                      }}
                    />
                    <path
                      d={path}
                      markerEnd={reject ? 'url(#machine-arrow-reject)' : 'url(#machine-arrow)'}
                      className={
                        'machine-line' +
                        (edge.id === selectedLineId ? ' is-selected' : '') +
                        (reject ? ' is-reject' : '') +
                        (edge.condition_key ? ' is-if' : '')
                      }
                    />
                  </g>
                );
              })}
            </svg>
            <div
              className="machine-flow"
              style={{
                gridTemplateColumns: `52px 72px repeat(${Math.max(columnRanks.length, 1)}, minmax(148px, 1fr)) 72px`,
                gridTemplateRows: `28px repeat(${rowCount}, minmax(92px, auto))`
              }}
            >
              <div className="machine-grid-corner" style={{ gridColumn: 1, gridRow: 1 }} />
              <div className="machine-col-head" style={{ gridColumn: 2, gridRow: 1 }}>
                Start
              </div>
              {columnRanks.map((order, index) => (
                <div
                  key={`col-head-${order}`}
                  className={`machine-col-head${parallelColumns.has(order) ? ' is-parallel' : ''}`}
                  style={{ gridColumn: index + 3, gridRow: 1 }}
                >
                  Col {order}
                  {parallelColumns.has(order) ? ' · parallel' : ''}
                </div>
              ))}
              <div className="machine-col-head is-done" style={{ gridColumn: columnRanks.length + 3, gridRow: 1 }}>
                End
              </div>
              {Array.from({ length: rowCount }, (_, index) => (
                <div key={`row-${index}`} className="machine-row-label" style={{ gridColumn: 1, gridRow: index + 2 }}>
                  Row {index + 1}
                </div>
              ))}
              {columnRanks.map((order, index) =>
                parallelColumns.has(order) ? (
                  <div key={`col-band-${order}`} className="machine-col-band" style={{ gridColumn: index + 3, gridRow: `2 / ${rowCount + 2}` }} />
                ) : null
              )}
              <div className="machine-terminal" style={{ gridColumn: 2, gridRow: 2 }}>
                Start
              </div>
              {stages.map((stage) => (
                <button
                  key={stage.id}
                  type="button"
                  data-node={stage.id}
                  style={{
                    gridColumn: columnRanks.indexOf(stage.order) + 3,
                    gridRow: stageRow(stage) + 1
                  }}
                  className={
                    'machine-node' +
                    (stage.id === selectedId ? ' is-selected' : '') +
                    (stage.id === drawingFrom ? ' is-drawing' : '') +
                    (stage.require_approval ? ' is-gated' : ' is-auto') +
                    (stage.confirm_writes ? ' is-confirm-writes' : '') +
                    (parallelColumns.has(stage.order) ? ' is-parallel' : '')
                  }
                  onClick={() => pickNode(stage.id)}
                  aria-pressed={stage.id === selectedId}
                >
                  <span className="machine-node-order">
                    C{stage.order} R{stageRow(stage)}
                    {parallelColumns.has(stage.order) ? ' · parallel' : ''}
                  </span>
                  <strong>{stage.name}</strong>
                  <span>
                    {stage.require_approval ? 'Human gate' : 'Auto-advance'}
                    {stage.confirm_writes ? ' · confirm writes' : ''}
                  </span>
                </button>
              ))}
              <button
                type="button"
                data-node={DONE_ID}
                className="machine-terminal is-done"
                style={{ gridColumn: columnRanks.length + 3, gridRow: 2 }}
                onClick={() => pickNode(DONE_ID)}
              >
                Done
              </button>
            </div>
          </div>
          <AddStageForm disabled={busy} pending={createStage.isPending} onAdd={(name) => createStage.mutate({ name })} />
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
              onToggleWrites={(confirmWrites) => updateStage.mutate({ confirm_writes: confirmWrites })}
              onDrawLine={() => {
                setDrawingFrom(selected.id);
                setSelectedLineId(null);
              }}
              onEditAgent={() => setAgentStage(selected)}
              onAddParallel={(name) => createStage.mutate({ name, parallel: true, from_stage_id: selected.id })}
              onPlace={(column, row) =>
                updateStage.mutate({
                  order: Math.max(1, column),
                  lane: freeLane(stages, Math.max(1, column), Math.max(1, row) - 1, selected.id)
                })
              }
              onDelete={() => setConfirmDelete(true)}
              onSelectLine={(id) => {
                setSelectedLineId(id);
                setSelectedId(null);
              }}
            />
          ) : (
            <p className="muted">
              Select a stage, then Draw line and click another stage. Place only moves the stage on the grid. Add parallel row or a second default line to run
              tracks at the same time.
            </p>
          )}
        </aside>
      </div>

      <CardLifecycleLegend machine={cardMachine} />

      <AgentConfigModal
        stage={agentStage}
        boardWorkspace={{ path: board.workspace_path ?? '', git_url: board.git_url ?? '' }}
        onClose={() => setAgentStage(null)}
      />

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
  onToggleWrites: (confirmWrites: boolean) => void;
  onDrawLine: () => void;
  onEditAgent: () => void;
  onAddParallel: (name: string) => void;
  onPlace: (column: number, row: number) => void;
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
  onToggleWrites,
  onDrawLine,
  onEditAgent,
  onAddParallel,
  onPlace,
  onDelete,
  onSelectLine
}: StageInspectorProps) {
  const [name, setName] = useState(stage.name);
  const [column, setColumn] = useState(stage.order);
  const [row, setRow] = useState(stageRow(stage));
  const [parallelName, setParallelName] = useState('');

  useEffect(() => {
    setName(stage.name);
    setColumn(stage.order);
    setRow((stage.lane ?? 0) + 1);
    setParallelName('');
  }, [stage.id, stage.name, stage.order, stage.lane]);

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
      <div className="machine-place">
        <label className="field">
          Column
          <input className="input" type="number" min={1} value={column} disabled={busy} onChange={(event) => setColumn(Number(event.target.value) || 1)} />
        </label>
        <label className="field">
          Row
          <input className="input" type="number" min={1} value={row} disabled={busy} onChange={(event) => setRow(Number(event.target.value) || 1)} />
        </label>
        <button type="button" className="btn" disabled={busy || (column === stage.order && row === stageRow(stage))} onClick={() => onPlace(column, row)}>
          Place
        </button>
      </div>
      <p className="muted">Place only sets column and row on the board. Cards still follow the lines below.</p>
      <div className="field">
        <span>Progression</span>
        <label className="tool-row">
          <input type="checkbox" checked={stage.require_approval} disabled={busy} onChange={(event) => onToggleGate(event.target.checked)} />
          Require human approval
        </label>
        <p className="muted">The agent may recommend approve or reject. The card still waits here until a human confirms.</p>
      </div>
      <div className="field">
        <span>Writes</span>
        <label className="tool-row">
          <input type="checkbox" checked={Boolean(stage.confirm_writes)} disabled={busy} onChange={(event) => onToggleWrites(event.target.checked)} />
          Confirm MCP writes
        </label>
        <p className="muted">
          Independent of the human gate. Reads run immediately. Create, comment, transition, PR, and other writes wait on this stage until you confirm them.
        </p>
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
      <label className="field">
        Parallel row after this stage
        <input
          className="input"
          value={parallelName}
          onChange={(event) => setParallelName(event.target.value)}
          placeholder="Unit tests or software"
          disabled={busy}
        />
      </label>
      <p className="muted">
        Adds a new row in the next column and a second default line so both tracks run. To join later, draw a line from each row into the same later column.
      </p>
      <div className="machine-inspector-actions">
        <button
          type="button"
          className="btn"
          disabled={busy || !parallelName.trim()}
          onClick={() => {
            const trimmed = parallelName.trim();
            if (trimmed) {
              onAddParallel(trimmed);
              setParallelName('');
            }
          }}
        >
          Add parallel row
        </button>
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

  const containsNeedsValue = op === 'contains' && key.trim().length > 0 && !value.trim();

  return (
    <form
      className="machine-inspector-form"
      onSubmit={(eventSubmit) => {
        eventSubmit.preventDefault();
        if (containsNeedsValue) {
          return;
        }
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
        <input className="input" value={key} onChange={(change) => setKey(change.target.value)} placeholder="recommendation or risk" disabled={busy} />
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
        Empty If is the default line. Several default lines from the same stage split into the next column&apos;s rows. Lines from two or more stages into one
        stage wait for every track, then merge. A matching If is exclusive and skips the defaults.
      </p>
      {containsNeedsValue ? <p className="error">Contains needs a non-empty value, or it would match every handoff.</p> : null}
      <div className="machine-inspector-actions">
        <button type="submit" className="btn btn-primary" disabled={busy || containsNeedsValue}>
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
  const states =
    machine?.states ?? (['idle', 'running', 'waiting_approval', 'waiting_tool_approval', 'waiting_join', 'blocked', 'done'] satisfies CardStatus[]);
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
