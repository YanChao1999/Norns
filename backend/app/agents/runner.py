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
from ..database import AsyncSessionLocal
from ..models import AgentRun, Board, Card, Connector, Stage
from ..orchestrator.enqueue import enqueue_stage_run
from ..orchestrator.progression import next_stage_after
from ..orchestrator.state_machine import CardStatus, auto_advance_card, start_card_run, wait_for_approval
from ..plantuml.renderer import render_plantuml
from ..tools.registry import RuntimeTool, create_default_registry


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
            selectinload(Card.current_stage),
        )
    )
    stage_result = await session.execute(select(Stage).where(Stage.id == stage_id).options(selectinload(Stage.agent_config)))
    connectors_result = await session.execute(select(Connector).where(Connector.is_active.is_(True)))

    card = card_result.scalar_one_or_none()
    stage = stage_result.scalar_one_or_none()
    connectors = list(connectors_result.scalars().all())
    if not card or not stage:
        raise ValueError("Card or stage not found")

    start_card_run(card)
    card.current_stage_id = stage.id

    run = AgentRun(id=run_id, card_id=card.id, stage_id=stage.id, status="running")
    session.add(run)
    await session.commit()

    registry = create_default_registry()
    allowlist = stage.agent_config.tool_allowlist if stage.agent_config else []
    runtime_tools = registry.get_runtime_tools(allowlist, connectors)
    run.inputs = _build_inputs(card)

    next_stage = None
    try:
        model_output, tool_calls, handoff = await _execute_agent(
            settings=settings,
            card=card,
            stage=stage,
            runtime_tools=runtime_tools,
        )
        run.tool_calls = tool_calls
        run.model_output = model_output
        run.handoff = handoff
        run.status = "completed"
        run.completed_at = datetime.utcnow()
        if stage.require_approval:
            wait_for_approval(card)
        else:
            next_stage = next_stage_after(card.board.stages, stage.id)
            auto_advance_card(card, next_stage.id if next_stage else None)
        await session.commit()
    except Exception as exc:
        run.status = "failed"
        run.model_output = f"Stage run failed: {exc}"
        run.handoff = {"summary": run.model_output, "links": [], "attachment_metadata": []}
        run.completed_at = datetime.utcnow()
        card.status = CardStatus.BLOCKED
        await session.commit()
        raise

    if next_stage:
        await enqueue_stage_run(card.id, next_stage.id)


def _build_inputs(card: Card) -> dict[str, Any]:
    previous = sorted(card.runs, key=lambda item: item.created_at or datetime.min)
    prior_handoff = previous[-1].handoff if previous else None
    return {
        "card": {"id": card.id, "title": card.title, "body": card.body, "external_id": card.external_id},
        "prior_handoff": prior_handoff,
    }


async def _execute_agent(
    settings: Any,
    card: Card,
    stage: Stage,
    runtime_tools: list[RuntimeTool],
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    if not settings.openai_api_key:
        summary = f"OpenAI API key not configured. Placeholder run created for stage '{stage.name}'."
        handoff = await _build_handoff(summary)
        return summary, [], handoff

    config = stage.agent_config
    system_prompt = config.system_prompt if config else "You are a focused orchestration stage agent."
    model = config.model if config else settings.default_model
    temperature = config.temperature if config else 0.7
    tools_payload = [tool.openai_tool for tool in runtime_tools]
    tool_map = {tool.name: tool for tool in runtime_tools}

    client = AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"Card title: {card.title}\n\n"
                f"Card body:\n{card.body}\n\n"
                f"Previous handoff:\n{json.dumps(_latest_handoff(card), indent=2)}"
            ),
        },
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


async def _build_handoff(model_output: str) -> dict[str, Any]:
    plantuml_source = _extract_plantuml(model_output)
    payload = {
        "summary": model_output[:1200],
        "links": re.findall(r"https?://\S+", model_output),
        "attachment_metadata": [],
    }
    if plantuml_source:
        payload["plantuml"] = {"source": plantuml_source, "svg": await render_plantuml(plantuml_source)}
    return payload


def _latest_handoff(card: Card) -> dict[str, Any] | None:
    if not card.runs:
        return None
    previous_runs = sorted(card.runs, key=lambda item: item.created_at or datetime.min)
    return previous_runs[-1].handoff


def _extract_plantuml(text: str) -> str | None:
    match = re.search(r"```(?:plantuml|puml)\n(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None
