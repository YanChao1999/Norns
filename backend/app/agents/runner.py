from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import get_settings
from ..connector_config import resolve_llm_credentials
from ..database import AsyncSessionLocal
from ..models import AgentRun, Board, Card, Connector, Stage
from ..orchestrator.enqueue import EnqueueError, enqueue_stage_run
from ..orchestrator.progression import resolve_routes
from ..orchestrator.split import apply_forward_routes, load_family_cards
from ..orchestrator.state_machine import CardStatus, start_card_run, wait_for_approval
from ..plantuml.renderer import render_plantuml
from ..tools.registry import RuntimeTool, create_default_registry

DECISION_INSTRUCTION = (
    "This stage has a human gate. You may recommend approve or reject, but you cannot move the card. "
    "A human must confirm before any line fires. End your response with exactly two lines:\n"
    "DECISION: approve\n"
    "REASON: <one sentence>\n"
    "Use DECISION: reject when the work should go back or stop."
)


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
    run = AgentRun(id=run_id, card_id=card.id, stage_id=stage.id, status="running")
    run.inputs = {
        "card": {"id": card.id, "title": card.title, "body": card.body, "external_id": card.external_id},
        "prior_handoff": prior_handoff,
    }
    session.add(run)
    await session.commit()

    registry = create_default_registry()
    allowlist = stage.agent_config.tool_allowlist if stage.agent_config else []
    runtime_tools = registry.get_runtime_tools(allowlist, connectors)

    next_jobs: list[tuple[str, str]] = []
    try:
        creds = resolve_llm_credentials(connectors, settings)
        model_output, tool_calls, handoff = await _execute_agent(
            settings=settings,
            card=card,
            stage=stage,
            runtime_tools=runtime_tools,
            api_key=creds.api_key,
            base_url=creds.base_url,
            default_model=creds.default_model,
        )
        run.tool_calls = tool_calls
        run.model_output = model_output
        run.handoff = handoff
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
    except Exception as exc:
        run.status = "failed"
        run.model_output = f"Stage run failed: {exc}"
        run.handoff = {"summary": run.model_output, "links": [], "attachment_metadata": []}
        run.completed_at = datetime.utcnow()
        card.status = CardStatus.BLOCKED
        await session.commit()
        raise

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
    model = config.model if config else resolved_model
    temperature = config.temperature if config else 0.7
    tools_payload = [tool.openai_tool for tool in runtime_tools]
    tool_map = {tool.name: tool for tool in runtime_tools}

    client = AsyncOpenAI(api_key=resolved_key.strip(), base_url=resolved_url)
    user_content = (
        f"Card title: {card.title}\n\n"
        f"Card body:\n{card.body}\n\n"
        f"Previous handoff:\n{json.dumps(_latest_handoff(card), indent=2)}"
    )
    if stage.require_approval:
        user_content = f"{user_content}\n\n{DECISION_INSTRUCTION}"
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    response = await client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=messages,
        tools=tools_payload or None,
    )
    message = response.choices[0].message
    executed_tool_calls: list[dict[str, Any]] = []

    if getattr(message, "tool_calls", None):
        messages.append(message.model_dump(exclude_none=True))
        for tool_call in message.tool_calls:
            runtime_tool = tool_map.get(tool_call.function.name)
            arguments = json.loads(tool_call.function.arguments or "{}")
            if runtime_tool is None:
                result: Any = {"error": f"Unknown or disallowed tool: {tool_call.function.name}"}
            else:
                result = await runtime_tool.execute(arguments)
            executed_tool_calls.append({"name": tool_call.function.name, "arguments": arguments, "result": result})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_call.function.name,
                    "content": json.dumps(result),
                }
            )
        response = await client.chat.completions.create(model=model, temperature=temperature, messages=messages)
        message = response.choices[0].message

    content = message.content or "No textual response returned by the model."
    handoff = await _build_handoff(content)
    return content, executed_tool_calls, handoff


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
