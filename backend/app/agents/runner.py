from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import get_settings
from ..connector_config import (
    credentials_for_provider,
    provider_label,
    resolve_llm_credentials,
    resolve_stage_model,
    uses_cursor_cloud_agent,
)
from ..cursor_api import run_cursor_cloud_agent
from ..database import AsyncSessionLocal
from ..faults import loop_tool_error_if_injected, runner_timeout_if_injected
from ..models import AgentRun, Board, Card, Connector, Stage
from ..orchestrator.enqueue import EnqueueError, enqueue_stage_run
from ..orchestrator.progression import resolve_routes
from ..orchestrator.split import apply_forward_routes, load_family_cards
from ..orchestrator.state_machine import CardStatus, start_card_run, wait_for_approval, wait_for_tool_approval
from ..plantuml.renderer import render_plantuml
from ..plugins.base import PluginContext
from ..plugins.catalog import cursor_mcp_servers
from ..plugins.tool_policy import is_write_tool
from ..tools.registry import RuntimeTool, create_default_registry
from ..workspace import resolve_workspace

logger = logging.getLogger("norns")

DECISION_INSTRUCTION = (
    "This stage has a human gate. The gate only blocks moving the card — it does not block tools. "
    "Call tools now to finish the card work (create the Jira issue, write the key back with norns_update_card, and so on). "
    "Do not defer tool calls until after approval. An empty search result is not a reason to stop; create or update next. "
    "You may recommend approve or reject, but you cannot move the card. "
    "A human must confirm before any line fires. End your response with exactly two lines:\n"
    "DECISION: approve\n"
    "REASON: <one sentence>\n"
    "Use DECISION: reject when the work should go back or stop."
)

WORK_INSTRUCTION = (
    "Use your tools in this run until the requested work is done or blocked. "
    "Empty list results mean nothing matched yet — continue with create/update/verify. "
    "Do not end with a plan of tool calls you did not make."
)

MAX_TOOL_ROUNDS = 8


def llm_identity(provider: str, model: str) -> dict[str, str]:
    return {"provider": str(provider or "").strip().lower(), "model": str(model or "").strip()}


def llm_line(identity: dict[str, Any] | None) -> str:
    if not identity:
        return ""
    provider = str(identity.get("provider") or "").strip()
    model = str(identity.get("model") or "").strip()
    if not provider and not model:
        return ""
    label = provider_label(provider)
    if model:
        return f"LLM: {label} · {model}"
    return f"LLM: {label}"


def with_llm_line(text: str, identity: dict[str, Any] | None) -> str:
    line = llm_line(identity)
    body = text or ""
    if not line or body.startswith("LLM:"):
        return body
    return f"{line}\n\n{body}" if body else line


def tool_error_text(exc: BaseException) -> str:
    if isinstance(exc, TimeoutError):
        return (
            "Cursor stage timed out waiting for the cloud agent. "
            "The card body is still the task — rerun, or set this stage to DeepSeek/OpenAI."
        )
    text = str(getattr(exc, "text", None) or "").strip()
    if not text:
        text = str(exc).split("response headers")[0].strip()
    status = getattr(exc, "status_code", None)
    if status:
        return f"HTTP {status}: {text}"
    return text or exc.__class__.__name__


class WriteConfirmationRequired(Exception):
    def __init__(self, pending: list[dict[str, Any]], executed: list[dict[str, Any]]) -> None:
        super().__init__("Write tools are waiting for Control Room confirmation")
        self.pending = pending
        self.executed = executed


async def run_stage(card_id: str, stage_id: str, run_id: str) -> None:
    async with AsyncSessionLocal() as session:
        await _run_stage(session, card_id, stage_id, run_id)


async def _run_stage(session: AsyncSession, card_id: str, stage_id: str, run_id: str) -> None:
    settings = get_settings()
    card_result = await session.execute(
        select(Card)
        .where(Card.id == card_id)
        .options(
            selectinload(Card.runs),
            selectinload(Card.board).selectinload(Board.stages).selectinload(Stage.agent_config),
            selectinload(Card.board).selectinload(Board.transitions),
            selectinload(Card.current_stage),
        )
    )
    stage_result = await session.execute(
        select(Stage).where(Stage.id == stage_id).options(selectinload(Stage.agent_config))
    )
    connectors_result = await session.execute(select(Connector).where(Connector.is_active.is_(True)))

    card = card_result.scalar_one_or_none()
    stage = stage_result.scalar_one_or_none()
    connectors = list(connectors_result.scalars().all())
    if not card or not stage:
        raise ValueError("Card or stage not found")
    if stage.board_id != card.board_id:
        raise ValueError("Stage does not belong to this card's board")

    start_card_run(card)
    card.current_stage_id = stage.id

    prior_handoff = _latest_handoff(card)
    workspace = resolve_workspace(connectors, agent=stage.agent_config, board=card.board)
    run = AgentRun(id=run_id, card_id=card.id, stage_id=stage.id, status="running")
    run.inputs = {
        "card": {"id": card.id, "title": card.title, "body": card.body, "external_id": card.external_id},
        "prior_handoff": prior_handoff,
        "workspace": {
            "path": workspace.path,
            "git_url": workspace.git_url,
            "github_repo": workspace.github_repo,
            "source": workspace.source,
        },
    }
    session.add(run)
    await session.commit()

    registry = create_default_registry()
    allowlist = stage.agent_config.tool_allowlist if stage.agent_config else []
    runtime_tools = registry.get_runtime_tools(
        allowlist,
        connectors,
        context=PluginContext(
            connectors=connectors,
            board_id=card.board_id,
            card_id=card.id,
            stage_id=stage.id,
            workspace_path=workspace.path,
            git_url=workspace.git_url,
            github_repo=workspace.github_repo,
        ),
    )
    mcp_preview = cursor_mcp_servers(allowlist, connectors)
    run.inputs = {
        **dict(run.inputs or {}),
        "plugins": {
            "allowlist": list(allowlist),
            "mcp_servers": list(mcp_preview.keys()),
            "tools": [tool.name for tool in runtime_tools],
            "jira_connector": any(
                connector.is_active and str(connector.connector_type.value) == "jira" for connector in connectors
            ),
        },
    }

    next_jobs: list[tuple[str, str]] = []
    try:
        preferred = ""
        if stage.agent_config and str(getattr(stage.agent_config, "llm_provider", "") or "").strip():
            preferred = str(stage.agent_config.llm_provider).strip().lower()
        if preferred:
            creds = credentials_for_provider(connectors, settings, preferred)
        else:
            creds = resolve_llm_credentials(connectors, settings)
        identity = llm_identity(
            creds.provider,
            resolve_stage_model(
                provider=creds.provider,
                base_url=creds.base_url,
                stage_model=(stage.agent_config.model if stage.agent_config else "") or creds.default_model,
                default_model=creds.default_model,
            ),
        )
        run.inputs = {**dict(run.inputs or {}), "llm": identity}
        runner_timeout_if_injected()
        model_output, tool_calls, handoff = await _execute_agent(
            settings=settings,
            card=card,
            stage=stage,
            runtime_tools=runtime_tools,
            api_key=creds.api_key,
            base_url=creds.base_url,
            default_model=creds.default_model,
            provider=creds.provider,
            repo_url=creds.repo_url,
            connectors=connectors,
            workspace=workspace,
            run_id=run.id,
            confirm_writes=bool(getattr(stage, "confirm_writes", False)),
        )
        await session.refresh(run)
        run.inputs = {**dict(run.inputs or {}), "llm": identity}
        pending = list((run.inputs or {}).get("pending_writes") or [])
        run.tool_calls = tool_calls
        run.model_output = with_llm_line(model_output, identity)
        run.handoff = {**(handoff if isinstance(handoff, dict) else {}), "llm": identity}
        if pending:
            run.status = "waiting_tool"
            wait_for_tool_approval(card)
            await session.commit()
            return
        run.status = "completed"
        run.completed_at = datetime.utcnow()
        if stage.require_approval:
            # Agent recommendation is advisory only; never skip the human gate.
            wait_for_approval(card)
        else:
            routes = resolve_routes(
                card.board.stages,
                card.board.transitions,
                stage.id,
                "auto",
                handoff if isinstance(handoff, dict) else {},
            )
            next_jobs = await apply_forward_routes(
                session,
                card,
                list(card.board.stages),
                routes,
                handoff if isinstance(handoff, dict) else {},
                auto=True,
                transitions=list(card.board.transitions),
                board_cards=await load_family_cards(session, card),
            )
        await session.commit()
    except WriteConfirmationRequired as pending:
        inputs = dict(run.inputs or {})
        inputs["pending_writes"] = pending.pending
        run.inputs = inputs
        identity = dict((run.inputs or {}).get("llm") or {})
        run.tool_calls = pending.executed
        run.model_output = with_llm_line("Write tools are waiting for Control Room confirmation.", identity)
        run.handoff = {
            "summary": run.model_output,
            "pending_writes": pending.pending,
            "llm": identity,
            "links": [],
            "attachment_metadata": [],
        }
        run.status = "waiting_tool"
        wait_for_tool_approval(card)
        await session.commit()
        return
    except Exception as exc:
        identity = dict((run.inputs or {}).get("llm") or {})
        detail = tool_error_text(exc)
        run.status = "failed"
        run.model_output = with_llm_line(f"Stage run stopped: {detail}", identity)
        run.handoff = {
            "summary": run.model_output,
            "llm": identity,
            "recommendation": "reject",
            "recommendation_reason": detail,
            "links": [],
            "attachment_metadata": [],
        }
        run.completed_at = datetime.utcnow()
        card.status = CardStatus.IDLE
        await session.commit()
        logger.warning("Stage run stopped card=%s stage=%s: %s", card.id, stage.id, detail)
        return

    for card_id, next_stage_id in next_jobs:
        try:
            await enqueue_stage_run(card_id, next_stage_id)
        except EnqueueError:
            stuck = await session.get(Card, card_id)
            if stuck:
                stuck.status = CardStatus.BLOCKED
                await session.commit()
            raise


def _latest_handoff(card: Card) -> dict[str, Any] | None:
    completed = [run for run in card.runs if run.status == "completed"]
    if not completed:
        return None
    previous_runs = sorted(completed, key=lambda item: item.created_at or datetime.min)
    return previous_runs[-1].handoff


async def _execute_agent(
    settings: Any,
    card: Card,
    stage: Stage,
    runtime_tools: list[RuntimeTool],
    *,
    api_key: str = "",
    base_url: str = "",
    default_model: str = "",
    provider: str = "",
    repo_url: str = "",
    connectors: list[Any] | None = None,
    workspace: Any | None = None,
    run_id: str = "",
    confirm_writes: bool = False,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    resolved_key = api_key or str(getattr(settings, "openai_api_key", "") or "")
    resolved_url = base_url or str(getattr(settings, "openai_base_url", "") or "https://api.openai.com/v1")
    resolved_model = default_model or str(getattr(settings, "default_model", "") or "gpt-4o")
    if not resolved_key.strip():
        summary = (
            f"This was a practice run for {stage.name} — no model API key is set, so no model was called. "
            "Add an OpenAI, Cursor, or DeepSeek connector in Settings and run again for a real agent."
        )
        handoff = await _build_handoff(summary)
        handoff["placeholder"] = True
        return summary, [], handoff

    config = stage.agent_config
    system_prompt = config.system_prompt if config else "You are a focused orchestration stage agent."
    stage_model = config.model if config else resolved_model
    model = resolve_stage_model(
        provider=provider,
        base_url=resolved_url,
        stage_model=stage_model,
        default_model=resolved_model,
    )
    temperature = config.temperature if config else 0.7
    workspace_bits = ""
    if workspace and (getattr(workspace, "path", "") or getattr(workspace, "git_url", "")):
        workspace_bits = (
            "\n\nGit workspace:\n"
            f"- local path: {getattr(workspace, 'path', '') or '(none)'}\n"
            f"- git url: {getattr(workspace, 'git_url', '') or '(none)'}\n"
            f"- github repo: {getattr(workspace, 'github_repo', '') or '(none)'}\n"
        )
    card_id = str(getattr(card, "id", "") or "")
    board_id = str(getattr(card, "board_id", "") or "")
    stage_id = str(getattr(stage, "id", "") or "")
    user_content = (
        f"Card id: {card_id}\n"
        f"Board id: {board_id}\n"
        f"Stage id: {stage_id}\n"
        f"Card title: {card.title}\n\n"
        f"Card body:\n{card.body}\n"
        f"{workspace_bits}\n"
        f"Previous handoff:\n{json.dumps(_latest_handoff(card), indent=2)}\n\n"
        f"{WORK_INSTRUCTION}"
    )
    if confirm_writes:
        user_content = (
            f"{user_content}\n\n"
            "This stage confirms writes in the Control Room. Search and read tools run now. "
            "Create, comment, transition, and other writes are queued until a human confirms them on this card."
        )
    if stage.require_approval:
        user_content = f"{user_content}\n\n{DECISION_INSTRUCTION}"

    if uses_cursor_cloud_agent(provider, resolved_url):
        extra_env = {
            "NORNS_BOARD_ID": str(getattr(card, "board_id", "") or ""),
            "NORNS_CARD_ID": str(getattr(card, "id", "") or ""),
            "NORNS_STAGE_ID": str(getattr(stage, "id", "") or ""),
            "NORNS_RUN_ID": str(run_id or ""),
        }
        if confirm_writes:
            extra_env["NORNS_CONFIRM_WRITES"] = "1"
        if workspace:
            if getattr(workspace, "path", ""):
                extra_env["NORNS_WORKSPACE"] = workspace.path
            if getattr(workspace, "git_url", ""):
                extra_env["NORNS_GIT_URL"] = workspace.git_url
            if getattr(workspace, "github_repo", ""):
                extra_env["NORNS_GITHUB_REPO"] = workspace.github_repo
        extra_env = {key: value for key, value in extra_env.items() if value}
        mcp_servers = cursor_mcp_servers(
            stage.agent_config.tool_allowlist if stage.agent_config else [],
            list(connectors or []),
            extra_env=extra_env or None,
            cwd=getattr(workspace, "path", "") or None,
        )
        attached = ", ".join(mcp_servers) if mcp_servers else "none"
        tool_hint = (
            f" Attached Norns MCP servers: {attached}. Call those tools now to operate Jira/GitHub/Norns until the card work is done. "
            "Empty search results mean nothing exists yet — create next, then verify. "
            "Do not use Cursor IDE catalog tools (CreateGoal, GetDynamicTools, GenerateImage) for Jira — they are not the Norns connector."
            if mcp_servers
            else (
                " This stage has no Norns plugins enabled (Agent → Tools allowlist is empty). "
                "You cannot create a Jira issue this run. Do not search the Cursor IDE tool catalog for Jira. "
                "Recommend reject and tell the operator: open this column's Agent button, enable jira (needs an active Jira connector in Settings), save, then rerun."
            )
        )
        prompt = (
            f"{system_prompt}\n\n"
            "You are running as a Norns stage agent. Produce a clear textual handoff for the next column. "
            "Do not modify repositories unless the task explicitly requires it."
            f"{tool_hint}\n\n"
            f"{user_content}"
        )
        content = await run_cursor_cloud_agent(
            api_key=resolved_key.strip(),
            prompt=prompt,
            model=model,
            base_url=resolved_url,
            repo_url=getattr(workspace, "git_url", "") or repo_url,
            mcp_servers=mcp_servers or None,
            workspace_path=getattr(workspace, "path", "") or "",
        )
        identity = llm_identity(provider, model)
        content = with_llm_line(content, identity)
        handoff = await _build_handoff(content)
        handoff["llm"] = identity
        return content, [], handoff

    tools_payload = [tool.openai_tool for tool in runtime_tools]
    tool_map = {tool.name: tool for tool in runtime_tools}

    client = AsyncOpenAI(api_key=resolved_key.strip(), base_url=resolved_url)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    content, executed_tool_calls = await _run_openai_tool_loop(
        client,
        model=model,
        temperature=temperature,
        messages=messages,
        tools_payload=tools_payload,
        tool_map=tool_map,
        confirm_writes=confirm_writes,
    )
    identity = llm_identity(provider, model)
    content = with_llm_line(content, identity)
    handoff = await _build_handoff(content)
    handoff["llm"] = identity
    return content, executed_tool_calls, handoff


async def _run_openai_tool_loop(
    client: Any,
    *,
    model: str,
    temperature: float,
    messages: list[dict[str, Any]],
    tools_payload: list[dict[str, Any]],
    tool_map: dict[str, RuntimeTool],
    confirm_writes: bool = False,
) -> tuple[str, list[dict[str, Any]]]:
    executed_tool_calls: list[dict[str, Any]] = []
    message: Any = None
    for _round in range(MAX_TOOL_ROUNDS):
        response = await client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=messages,
            tools=tools_payload or None,
        )
        message = response.choices[0].message
        tool_calls = getattr(message, "tool_calls", None) or []
        if not tool_calls:
            break
        messages.append(message.model_dump(exclude_none=True))
        pending_writes: list[dict[str, Any]] = []
        for tool_call in tool_calls:
            name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments or "{}")
            if confirm_writes and is_write_tool(name):
                pending_writes.append({"name": name, "arguments": arguments})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": name,
                        "content": json.dumps(
                            {
                                "status": "pending_approval",
                                "message": "Write queued for Control Room confirmation.",
                            }
                        ),
                    }
                )
                continue
            runtime_tool = tool_map.get(name)
            if runtime_tool is None:
                result: Any = {"error": f"Unknown or disallowed tool: {name}"}
            else:
                injected = loop_tool_error_if_injected(name)
                if injected is not None:
                    result = injected
                else:
                    try:
                        result = await runtime_tool.execute(arguments)
                    except Exception as exc:
                        result = {"error": tool_error_text(exc)}
            executed_tool_calls.append({"round": _round + 1, "name": name, "arguments": arguments, "result": result})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": name,
                    "content": json.dumps(result, default=str),
                }
            )
        if pending_writes:
            raise WriteConfirmationRequired(pending_writes, executed_tool_calls)
    else:
        response = await client.chat.completions.create(model=model, temperature=temperature, messages=messages)
        message = response.choices[0].message

    content = (getattr(message, "content", None) if message is not None else None) or (
        "No textual response returned by the model."
    )
    return content, executed_tool_calls


def parse_agent_recommendation(model_output: str) -> tuple[str | None, str | None]:
    text = model_output or ""
    decision: str | None = None
    reason: str | None = None

    marked = re.search(
        r"(?im)^\s*(?:decision|recommendation|recommend)\s*[:=]\s*(approve|reject)\b",
        text,
    )
    if marked:
        decision = marked.group(1).lower()

    reason_match = re.search(r"(?im)^\s*(?:reason|because)\s*[:=]\s*(.+)$", text)
    if reason_match:
        reason = reason_match.group(1).strip().strip("*").strip() or None

    if decision is None:
        for blob in re.finditer(r"\{[^{}]+\}", text):
            try:
                data = json.loads(blob.group(0))
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue
            value = data.get("recommendation") or data.get("decision")
            if isinstance(value, str) and value.lower() in {"approve", "reject"}:
                decision = value.lower()
                json_reason = data.get("recommendation_reason") or data.get("reason")
                if isinstance(json_reason, str) and json_reason.strip():
                    reason = json_reason.strip()
                break

    return decision, reason


async def _build_handoff(model_output: str) -> dict[str, Any]:
    plantuml_source = _extract_plantuml(model_output)
    payload: dict[str, Any] = {
        "summary": model_output[:1200],
        "links": re.findall(r"https?://\S+", model_output),
        "attachment_metadata": [],
    }
    decision, reason = parse_agent_recommendation(model_output)
    if decision:
        payload["recommendation"] = decision
        if reason:
            payload["recommendation_reason"] = reason
    if plantuml_source:
        payload["plantuml"] = {"source": plantuml_source, "svg": await render_plantuml(plantuml_source)}
    return payload


def _extract_plantuml(text: str) -> str | None:
    match = re.search(r"```(?:plantuml|puml)\n(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None
