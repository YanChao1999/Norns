from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..database import AsyncSessionLocal
from ..models import AgentConfig, Board, Card, Stage, StageTransition
from .base import Plugin, PluginContext, ToolSpec

OBJECT = {"type": "object", "properties": {}}


def _apply_run_ids(arguments: dict[str, Any], context: PluginContext | None) -> dict[str, Any]:
    """Fill board/card/stage ids from the MCP/stage run when the model omits them."""
    if context is None:
        return dict(arguments)
    merged = dict(arguments)
    if not str(merged.get("board_id") or "").strip() and context.board_id:
        merged["board_id"] = context.board_id
    if not str(merged.get("card_id") or "").strip() and context.card_id:
        merged["card_id"] = context.card_id
    if not str(merged.get("stage_id") or "").strip() and context.stage_id:
        merged["stage_id"] = context.stage_id
    return merged


def _bind(execute, context: PluginContext, *, with_context: bool = False, apply_ids: bool = True):
    async def bound(arguments: dict[str, Any]) -> Any:
        args = _apply_run_ids(arguments, context) if apply_ids else dict(arguments)
        if with_context:
            return await execute(args, context)
        return await execute(args)

    return bound


class NornsPlugin(Plugin):
    name = "norns"
    title = "Norns"
    description = "Operate this Control Room: cards, stages, prompts, and state-machine transitions."
    builtin = True
    requires_connector = None

    def tools(self, context: PluginContext) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="norns_get_workspace",
                description="Show the git workspace for this stage agent, or a board (local path and remote URL).",
                input_schema={
                    "type": "object",
                    "properties": {
                        "board_id": {"type": "string"},
                        "stage_id": {"type": "string"},
                    },
                },
                execute=_bind(_get_workspace, context, with_context=True, apply_ids=False),
            ),
            ToolSpec(
                name="norns_git_status",
                description="Run git status in the workspace checkout for this agent or board.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "board_id": {"type": "string"},
                        "stage_id": {"type": "string"},
                    },
                },
                execute=_bind(_git_status, context, with_context=True, apply_ids=False),
            ),
            ToolSpec(
                name="norns_set_board_workspace",
                description="Bind a git repo to a board (local checkout path and/or remote URL). Stage agents inherit this unless they set their own.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "board_id": {"type": "string"},
                        "workspace_path": {"type": "string"},
                        "git_url": {"type": "string"},
                    },
                    "required": ["board_id"],
                },
                execute=_bind(_set_board_workspace, context),
            ),
            ToolSpec(
                name="norns_list_boards",
                description="List Norns boards (id, name, description).",
                input_schema={**OBJECT},
                execute=_bind(_list_boards, context),
            ),
            ToolSpec(
                name="norns_get_board",
                description="Get a board with stages, transitions, and cards.",
                input_schema={
                    "type": "object",
                    "properties": {"board_id": {"type": "string"}},
                    "required": ["board_id"],
                },
                execute=_bind(_get_board, context),
            ),
            ToolSpec(
                name="norns_list_cards",
                description="List cards on a board.",
                input_schema={
                    "type": "object",
                    "properties": {"board_id": {"type": "string"}},
                    "required": ["board_id"],
                },
                execute=_bind(_list_cards, context),
            ),
            ToolSpec(
                name="norns_create_card",
                description=(
                    "Create a workable Norns card on this board. "
                    "For a Polarion requirement, set title, body to the description, and external_id to the Polarion id."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "board_id": {"type": "string"},
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                        "external_id": {"type": "string"},
                    },
                    "required": ["title"] if context and context.board_id else ["board_id", "title"],
                },
                execute=_bind(_create_card, context),
            ),
            ToolSpec(
                name="norns_update_card",
                description="Update a card title, body, or external id.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "card_id": {"type": "string"},
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                        "external_id": {"type": "string"},
                    },
                    "required": ["card_id"],
                },
                execute=_bind(_update_card, context),
            ),
            ToolSpec(
                name="norns_update_stage_prompt",
                description="Replace a stage agent's system prompt.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "stage_id": {"type": "string"},
                        "system_prompt": {"type": "string"},
                    },
                    "required": ["stage_id", "system_prompt"],
                },
                execute=_bind(_update_stage_prompt, context),
            ),
            ToolSpec(
                name="norns_update_stage",
                description="Edit a stage (name, gate, model, tools, prompt).",
                input_schema={
                    "type": "object",
                    "properties": {
                        "stage_id": {"type": "string"},
                        "name": {"type": "string"},
                        "require_approval": {"type": "boolean"},
                        "confirm_writes": {
                            "type": "boolean",
                            "description": "If true, create/comment/transition and other writes wait for Control Room confirmation.",
                        },
                        "system_prompt": {"type": "string"},
                        "model": {"type": "string"},
                        "llm_provider": {"type": "string"},
                        "temperature": {"type": "number"},
                        "tool_allowlist": {"type": "array", "items": {"type": "string"}},
                        "workspace_path": {
                            "type": "string",
                            "description": "Optional git checkout for this agent only. Empty inherits the board workspace.",
                        },
                        "git_url": {"type": "string"},
                    },
                    "required": ["stage_id"],
                },
                execute=_bind(_update_stage, context),
            ),
            ToolSpec(
                name="norns_add_stage",
                description="Add a stage (column) to a board.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "board_id": {"type": "string"},
                        "name": {"type": "string"},
                        "order": {"type": "integer"},
                        "lane": {"type": "integer"},
                        "require_approval": {"type": "boolean"},
                        "system_prompt": {"type": "string"},
                    },
                    "required": ["board_id", "name"],
                },
                execute=_bind(_add_stage, context),
            ),
            ToolSpec(
                name="norns_add_transition",
                description="Add a state-machine line between stages (approve, reject, or auto).",
                input_schema={
                    "type": "object",
                    "properties": {
                        "board_id": {"type": "string"},
                        "from_stage_id": {"type": "string"},
                        "to_stage_id": {"type": "string"},
                        "event": {"type": "string", "description": "approve, reject, or auto"},
                        "condition_key": {"type": "string"},
                        "condition_op": {"type": "string"},
                        "condition_value": {"type": "string"},
                    },
                    "required": ["board_id", "from_stage_id", "to_stage_id"],
                },
                execute=_bind(_add_transition, context),
            ),
            ToolSpec(
                name="norns_update_transition",
                description="Edit a state-machine transition line.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "transition_id": {"type": "string"},
                        "from_stage_id": {"type": "string"},
                        "to_stage_id": {"type": "string"},
                        "event": {"type": "string"},
                        "condition_key": {"type": "string"},
                        "condition_op": {"type": "string"},
                        "condition_value": {"type": "string"},
                        "order": {"type": "integer"},
                    },
                    "required": ["transition_id"],
                },
                execute=_bind(_update_transition, context),
            ),
            ToolSpec(
                name="norns_delete_transition",
                description="Delete a state-machine transition line.",
                input_schema={
                    "type": "object",
                    "properties": {"transition_id": {"type": "string"}},
                    "required": ["transition_id"],
                },
                execute=_bind(_delete_transition, context),
            ),
        ]


async def _get_workspace(arguments: dict[str, Any], context: PluginContext | None = None) -> Any:
    from sqlalchemy import select as select_stmt
    from sqlalchemy.orm import selectinload as load

    from ..models.connector import Connector
    from ..workspace import resolve_workspace, serialize_workspace

    board_id = str(arguments.get("board_id") or "").strip()
    stage_id = str(arguments.get("stage_id") or "").strip()
    if not board_id and not stage_id:
        if context and (context.workspace_path or context.git_url):
            from ..workspace import Workspace

            found = Workspace(path=context.workspace_path, git_url=context.git_url, source="context")
            return serialize_workspace(found)
        if context:
            board_id = str(context.board_id or "").strip()
            stage_id = str(context.stage_id or "").strip()

    async with AsyncSessionLocal() as session:
        result = await session.execute(select_stmt(Connector).where(Connector.is_active.is_(True)))
        connectors = list(result.scalars().all())
        board = None
        agent = None
        if stage_id:
            stage_result = await session.execute(
                select_stmt(Stage).where(Stage.id == stage_id).options(load(Stage.agent_config), load(Stage.board))
            )
            stage = stage_result.scalar_one_or_none()
            if stage is None:
                return {"error": "Stage not found"}
            agent = stage.agent_config
            board = stage.board
        elif board_id:
            board = await session.get(Board, board_id)
            if board is None:
                return {"error": "Board not found"}
        found = resolve_workspace(connectors, agent=agent, board=board)
    return serialize_workspace(found)


async def _git_status(arguments: dict[str, Any], context: PluginContext | None = None) -> Any:
    import asyncio
    from pathlib import Path

    info = await _get_workspace(arguments, context)
    if info.get("error"):
        return info
    root = info.get("path")
    if not root or not Path(str(root)).is_dir():
        return {"error": "No local git workspace. Set a checkout path on this board or this agent."}

    def _call() -> str:
        import subprocess

        completed = subprocess.run(
            ["git", "status", "--short", "--branch"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        return output.strip() or f"git status exited {completed.returncode}"

    return {"path": root, "status": await asyncio.to_thread(_call)}


async def _set_board_workspace(arguments: dict[str, Any]) -> Any:
    async with AsyncSessionLocal() as session:
        board = await session.get(Board, arguments["board_id"])
        if board is None:
            return {"error": "Board not found"}
        if "workspace_path" in arguments and arguments["workspace_path"] is not None:
            board.workspace_path = str(arguments["workspace_path"]).strip()
        if "git_url" in arguments and arguments["git_url"] is not None:
            board.git_url = str(arguments["git_url"]).strip()
        await session.commit()
        return _board_summary(board)


async def _list_boards(arguments: dict[str, Any]) -> Any:
    del arguments
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Board).order_by(Board.created_at))
        return [_board_summary(board) for board in result.scalars().all()]


async def _get_board(arguments: dict[str, Any]) -> Any:
    async with AsyncSessionLocal() as session:
        board = await _load_board(session, arguments["board_id"])
        if board is None:
            return {"error": "Board not found"}
        return {
            **_board_summary(board),
            "stages": [_stage_payload(stage) for stage in board.stages],
            "transitions": [_transition_payload(edge) for edge in board.transitions],
            "cards": [_card_payload(card) for card in board.cards],
        }


async def _list_cards(arguments: dict[str, Any]) -> Any:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Card).where(Card.board_id == arguments["board_id"]).order_by(Card.created_at)
        )
        return [_card_payload(card) for card in result.scalars().all()]


async def _create_card(arguments: dict[str, Any]) -> Any:
    async with AsyncSessionLocal() as session:
        board_id = str(arguments.get("board_id") or "").strip()
        if not board_id:
            return {"error": "board_id is required"}
        board = await _load_board(session, board_id)
        if board is None:
            return {"error": "Board not found"}
        stages = sorted(board.stages, key=lambda stage: stage.order)
        if not stages:
            return {"error": "Board has no stages"}
        card = Card(
            board_id=board.id,
            title=str(arguments["title"]).strip(),
            body=str(arguments.get("body") or ""),
            external_id=(str(arguments["external_id"]).strip() if arguments.get("external_id") else None),
            current_stage_id=stages[0].id,
        )
        session.add(card)
        await session.commit()
        await session.refresh(card)
        return _card_payload(card)


async def _update_card(arguments: dict[str, Any]) -> Any:
    async with AsyncSessionLocal() as session:
        card = await session.get(Card, arguments["card_id"])
        if card is None:
            return {"error": "Card not found"}
        if "title" in arguments and arguments["title"] is not None:
            card.title = str(arguments["title"]).strip()
        if "body" in arguments and arguments["body"] is not None:
            card.body = str(arguments["body"])
        if "external_id" in arguments:
            value = arguments["external_id"]
            card.external_id = str(value).strip() if value else None
        await session.commit()
        await session.refresh(card)
        return _card_payload(card)


async def _update_stage_prompt(arguments: dict[str, Any]) -> Any:
    return await _update_stage({"stage_id": arguments["stage_id"], "system_prompt": arguments["system_prompt"]})


async def _update_stage(arguments: dict[str, Any]) -> Any:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Stage).where(Stage.id == arguments["stage_id"]).options(selectinload(Stage.agent_config))
        )
        stage = result.scalar_one_or_none()
        if stage is None:
            return {"error": "Stage not found"}
        if arguments.get("name"):
            stage.name = str(arguments["name"]).strip()
        if "require_approval" in arguments and arguments["require_approval"] is not None:
            stage.require_approval = bool(arguments["require_approval"])
        if "confirm_writes" in arguments and arguments["confirm_writes"] is not None:
            stage.confirm_writes = bool(arguments["confirm_writes"])
        config_keys = (
            "system_prompt",
            "model",
            "llm_provider",
            "temperature",
            "tool_allowlist",
            "workspace_path",
            "git_url",
        )
        if any(key in arguments and arguments[key] is not None for key in config_keys):
            if stage.agent_config is None:
                stage.agent_config = AgentConfig(stage_id=stage.id)
            if arguments.get("system_prompt") is not None:
                stage.agent_config.system_prompt = str(arguments["system_prompt"])
            if arguments.get("model") is not None:
                stage.agent_config.model = str(arguments["model"])
            if arguments.get("llm_provider") is not None:
                stage.agent_config.llm_provider = str(arguments["llm_provider"])
            if arguments.get("temperature") is not None:
                stage.agent_config.temperature = float(arguments["temperature"])
            if arguments.get("tool_allowlist") is not None:
                stage.agent_config.tool_allowlist = [str(item) for item in arguments["tool_allowlist"]]
            if arguments.get("workspace_path") is not None:
                stage.agent_config.workspace_path = str(arguments["workspace_path"]).strip()
            if arguments.get("git_url") is not None:
                stage.agent_config.git_url = str(arguments["git_url"]).strip()
        await session.commit()
        result = await session.execute(
            select(Stage).where(Stage.id == stage.id).options(selectinload(Stage.agent_config))
        )
        return _stage_payload(result.scalar_one())


async def _add_stage(arguments: dict[str, Any]) -> Any:
    async with AsyncSessionLocal() as session:
        board = await _load_board(session, arguments["board_id"])
        if board is None:
            return {"error": "Board not found"}
        order = arguments.get("order")
        if order is None:
            order = max((stage.order for stage in board.stages), default=0) + 1
        stage = Stage(
            board_id=board.id,
            name=str(arguments["name"]).strip(),
            order=int(order),
            lane=int(arguments.get("lane") or 0),
            require_approval=bool(arguments["require_approval"]) if "require_approval" in arguments else True,
        )
        prompt = str(arguments.get("system_prompt") or "You are the stage agent. Produce a concise handoff.")
        stage.agent_config = AgentConfig(system_prompt=prompt, model="gpt-4o", temperature=0.7, tool_allowlist=[])
        session.add(stage)
        await session.commit()
        result = await session.execute(
            select(Stage).where(Stage.id == stage.id).options(selectinload(Stage.agent_config))
        )
        return _stage_payload(result.scalar_one())


async def _add_transition(arguments: dict[str, Any]) -> Any:
    event = str(arguments.get("event") or "approve").strip().lower()
    if event not in {"approve", "reject", "auto"}:
        return {"error": "event must be approve, reject, or auto"}
    async with AsyncSessionLocal() as session:
        board = await session.get(Board, arguments["board_id"])
        if board is None:
            return {"error": "Board not found"}
        edge = StageTransition(
            board_id=board.id,
            from_stage_id=str(arguments["from_stage_id"]),
            to_stage_id=str(arguments["to_stage_id"]) if arguments.get("to_stage_id") else None,
            event=event,
            condition_key=str(arguments.get("condition_key") or ""),
            condition_op=str(arguments.get("condition_op") or "eq"),
            condition_value=str(arguments.get("condition_value") or ""),
        )
        session.add(edge)
        await session.commit()
        await session.refresh(edge)
        return _transition_payload(edge)


async def _update_transition(arguments: dict[str, Any]) -> Any:
    async with AsyncSessionLocal() as session:
        edge = await session.get(StageTransition, arguments["transition_id"])
        if edge is None:
            return {"error": "Transition not found"}
        for field in ("from_stage_id", "to_stage_id", "event", "condition_key", "condition_op", "condition_value"):
            if field in arguments and arguments[field] is not None:
                setattr(edge, field, arguments[field])
        if arguments.get("order") is not None:
            edge.order = int(arguments["order"])
        await session.commit()
        await session.refresh(edge)
        return _transition_payload(edge)


async def _delete_transition(arguments: dict[str, Any]) -> Any:
    async with AsyncSessionLocal() as session:
        edge = await session.get(StageTransition, arguments["transition_id"])
        if edge is None:
            return {"error": "Transition not found"}
        await session.delete(edge)
        await session.commit()
        return {"deleted": True, "transition_id": arguments["transition_id"]}


async def _load_board(session, board_id: str) -> Board | None:
    result = await session.execute(
        select(Board)
        .where(Board.id == board_id)
        .options(
            selectinload(Board.stages).selectinload(Stage.agent_config),
            selectinload(Board.transitions),
            selectinload(Board.cards),
        )
    )
    return result.scalar_one_or_none()


def _board_summary(board: Board) -> dict[str, Any]:
    return {
        "id": board.id,
        "name": board.name,
        "description": board.description,
        "workspace_path": board.workspace_path or "",
        "git_url": board.git_url or "",
    }


def _stage_payload(stage: Stage) -> dict[str, Any]:
    config = stage.agent_config
    return {
        "id": stage.id,
        "board_id": stage.board_id,
        "name": stage.name,
        "order": stage.order,
        "lane": stage.lane,
        "require_approval": stage.require_approval,
        "confirm_writes": bool(getattr(stage, "confirm_writes", False)),
        "system_prompt": config.system_prompt if config else None,
        "model": config.model if config else None,
        "llm_provider": config.llm_provider if config else None,
        "tool_allowlist": list(config.tool_allowlist) if config else [],
        "workspace_path": config.workspace_path if config else "",
        "git_url": config.git_url if config else "",
    }


def _card_payload(card: Card) -> dict[str, Any]:
    return {
        "id": card.id,
        "board_id": card.board_id,
        "title": card.title,
        "body": card.body,
        "external_id": card.external_id,
        "current_stage_id": card.current_stage_id,
        "status": str(card.status),
    }


def _transition_payload(edge: StageTransition) -> dict[str, Any]:
    return {
        "id": edge.id,
        "board_id": edge.board_id,
        "from_stage_id": edge.from_stage_id,
        "to_stage_id": edge.to_stage_id,
        "event": edge.event,
        "condition_key": edge.condition_key,
        "condition_op": edge.condition_op,
        "condition_value": edge.condition_value,
        "order": edge.order,
    }
