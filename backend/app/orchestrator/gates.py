from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from ..models import Approval, Board, Card, Connector, Stage
from ..plugins.base import PluginContext, apply_run_ids
from .enqueue import EnqueueError, enqueue_stage_run
from .progression import resolve_route, resolve_routes
from .split import apply_forward_routes, load_family_cards
from .state_machine import CardStatus, reject_card_state, return_card_to_stage, start_card_run


async def _load_card_for_gate(session: AsyncSession, card_id: str) -> Card:
    result = await session.execute(
        select(Card)
        .where(Card.id == card_id)
        .options(
            selectinload(Card.current_stage).selectinload(Stage.board).selectinload(Board.stages),
            selectinload(Card.current_stage).selectinload(Stage.board).selectinload(Board.transitions),
            selectinload(Card.runs),
        )
    )
    card = result.scalar_one_or_none()
    if not card:
        raise ValueError("Card not found")
    if card.status != CardStatus.WAITING_APPROVAL:
        raise ValueError("Card is not waiting for approval")
    if not card.current_stage:
        raise ValueError("Card has no current stage")
    return card


def _latest_stage_run(card: Card):
    return next(
        (
            run
            for run in sorted(card.runs, key=lambda item: (item.created_at or datetime.min, item.id), reverse=True)
            if run.stage_id == card.current_stage_id
        ),
        None,
    )


def _write_plugin_context(card: Card, run, connectors: list[Connector]) -> PluginContext:
    workspace = dict((run.inputs or {}).get("workspace") or {})
    return PluginContext(
        connectors=connectors,
        board_id=card.board_id,
        card_id=card.id,
        stage_id=card.current_stage_id,
        workspace_path=str(workspace.get("path") or ""),
        git_url=str(workspace.get("git_url") or ""),
        github_repo=str(workspace.get("github_repo") or ""),
    )


async def approve_card(session: AsyncSession, card_id: str, actor: str, comment: str | None = None) -> Approval:
    card = await _load_card_for_gate(session, card_id)
    latest_run = _latest_stage_run(card)
    if not latest_run:
        raise ValueError("No agent run available for approval")

    approval = Approval(
        card_id=card.id,
        stage_id=card.current_stage_id,
        agent_run_id=latest_run.id,
        actor=actor,
        approved=True,
        comment=comment,
    )
    session.add(approval)

    board = card.current_stage.board
    handoff = latest_run.handoff if isinstance(latest_run.handoff, dict) else {}
    routes = resolve_routes(board.stages, board.transitions, card.current_stage_id, "approve", handoff)
    family = await load_family_cards(session, card)
    queued = await apply_forward_routes(
        session,
        card,
        list(board.stages),
        routes,
        handoff,
        auto=False,
        transitions=list(board.transitions),
        board_cards=family,
    )
    await session.commit()
    await session.refresh(approval)

    for card_id, stage_id in queued:
        try:
            await enqueue_stage_run(card_id, stage_id)
        except EnqueueError:
            stuck = await session.get(Card, card_id)
            if stuck:
                stuck.status = CardStatus.BLOCKED
                await session.commit()
            raise
    return approval


async def reject_card(session: AsyncSession, card_id: str, actor: str, comment: str | None = None) -> Approval:
    card = await _load_card_for_gate(session, card_id)
    latest_run = _latest_stage_run(card)
    if not latest_run:
        raise ValueError("No agent run available for approval")

    approval = Approval(
        card_id=card.id,
        stage_id=card.current_stage_id,
        agent_run_id=latest_run.id,
        actor=actor,
        approved=False,
        comment=comment,
    )
    session.add(approval)
    board = card.current_stage.board
    route = resolve_route(
        board.stages,
        board.transitions,
        card.current_stage_id,
        "reject",
        latest_run.handoff if isinstance(latest_run.handoff, dict) else {},
    )
    if route.found and route.stage_id:
        return_card_to_stage(card, route.stage_id)
    elif route.found:
        card.status = CardStatus.DONE
    else:
        reject_card_state(card)
    await session.commit()
    await session.refresh(approval)
    return approval


async def _load_card_for_writes(session: AsyncSession, card_id: str) -> Card:
    result = await session.execute(
        select(Card)
        .where(Card.id == card_id)
        .options(
            selectinload(Card.current_stage).selectinload(Stage.agent_config),
            selectinload(Card.runs),
        )
    )
    card = result.scalar_one_or_none()
    if not card:
        raise ValueError("Card not found")
    if card.status != CardStatus.WAITING_TOOL_APPROVAL:
        raise ValueError("Card is not waiting for write confirmation")
    if not card.current_stage:
        raise ValueError("Card has no current stage")
    return card


async def approve_pending_writes(
    session: AsyncSession, card_id: str, actor: str, comment: str | None = None
) -> Approval:
    card = await _load_card_for_writes(session, card_id)
    latest_run = _latest_stage_run(card)
    if not latest_run:
        raise ValueError("No agent run available for write confirmation")
    inputs = dict(latest_run.inputs or {})
    pending = list(inputs.get("pending_writes") or [])
    if not pending:
        raise ValueError("No pending writes to confirm")

    from ..tools.registry import create_default_registry

    connectors_result = await session.execute(select(Connector).where(Connector.is_active.is_(True)))
    connectors = list(connectors_result.scalars().all())
    allowlist = list(card.current_stage.agent_config.tool_allowlist) if card.current_stage.agent_config else []
    context = _write_plugin_context(card, latest_run, connectors)
    tool_map = {
        tool.name: tool for tool in create_default_registry().get_runtime_tools(allowlist, connectors, context=context)
    }
    executed = list(latest_run.tool_calls or [])
    confirmed: list[dict] = []
    for index, item in enumerate(pending):
        name = str(item.get("name") or "")
        raw_arguments = item.get("arguments") if isinstance(item.get("arguments"), dict) else {}
        arguments = apply_run_ids(raw_arguments, context)
        runtime = tool_map.get(name)
        if runtime is None:
            result: object = {"error": f"Unknown or disallowed tool: {name}"}
        else:
            result = await runtime.execute(arguments)
        executed.append({"name": name, "arguments": arguments, "result": result})
        if isinstance(result, dict) and result.get("error"):
            remaining = list(pending[index:])
            remaining[0] = {**dict(item), "arguments": arguments, "error": result.get("error"), "status": "failed"}
            inputs["pending_writes"] = remaining
            inputs["confirmed_writes"] = confirmed
            latest_run.inputs = inputs
            flag_modified(latest_run, "inputs")
            latest_run.tool_calls = executed
            await session.commit()
            raise ValueError(f"Write {name} failed: {result.get('error')}. Remaining writes were not executed.")
        confirmed.append({**dict(item), "arguments": arguments})
        if isinstance(result, dict) and result.get("key"):
            card.external_id = str(result["key"])

    inputs["pending_writes"] = []
    inputs["confirmed_writes"] = confirmed
    latest_run.inputs = inputs
    flag_modified(latest_run, "inputs")
    latest_run.tool_calls = executed
    latest_run.status = "completed"
    latest_run.completed_at = datetime.utcnow()
    latest_run.handoff = {
        **(latest_run.handoff if isinstance(latest_run.handoff, dict) else {}),
        "summary": "Operator confirmed pending writes. Re-running this stage to verify.",
        "pending_writes": [],
    }
    approval = Approval(
        card_id=card.id,
        stage_id=card.current_stage_id,
        agent_run_id=latest_run.id,
        actor=actor,
        approved=True,
        comment=comment or "Confirmed pending writes",
    )
    session.add(approval)
    start_card_run(card)
    await session.commit()
    await session.refresh(approval)
    try:
        await enqueue_stage_run(card.id, card.current_stage_id)
    except EnqueueError:
        card.status = CardStatus.BLOCKED
        await session.commit()
        raise
    return approval


async def reject_pending_writes(
    session: AsyncSession, card_id: str, actor: str, comment: str | None = None
) -> Approval:
    card = await _load_card_for_writes(session, card_id)
    latest_run = _latest_stage_run(card)
    if not latest_run:
        raise ValueError("No agent run available for write confirmation")
    inputs = dict(latest_run.inputs or {})
    pending = list(inputs.get("pending_writes") or [])
    inputs["pending_writes"] = []
    inputs["rejected_writes"] = pending
    latest_run.inputs = inputs
    flag_modified(latest_run, "inputs")
    latest_run.status = "completed"
    latest_run.completed_at = datetime.utcnow()
    latest_run.handoff = {
        **(latest_run.handoff if isinstance(latest_run.handoff, dict) else {}),
        "summary": "Operator declined pending writes.",
        "pending_writes": [],
    }
    approval = Approval(
        card_id=card.id,
        stage_id=card.current_stage_id,
        agent_run_id=latest_run.id,
        actor=actor,
        approved=False,
        comment=comment or "Declined pending writes",
    )
    session.add(approval)
    reject_card_state(card)
    await session.commit()
    await session.refresh(approval)
    return approval
