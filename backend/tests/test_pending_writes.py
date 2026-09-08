from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.database import Base
from backend.app.models import AgentConfig, AgentRun, Board, Card, Stage
from backend.app.orchestrator.gates import approve_pending_writes, reject_pending_writes
from backend.app.orchestrator.state_machine import CardStatus
from backend.app.plugins.base import PluginContext
from backend.app.tools.registry import RuntimeTool


async def _session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, SessionLocal


@pytest.mark.asyncio
async def test_approve_pending_writes_fills_run_context(monkeypatch):
    engine, SessionLocal = await _session_factory()
    seen: dict[str, object] = {}

    class FakeRegistry:
        def get_runtime_tools(self, allowlist, connectors, context=None):
            seen["context"] = context
            seen["allowlist"] = list(allowlist)

            async def execute(arguments: dict) -> dict:
                seen["arguments"] = arguments
                return {"ok": True}

            return [RuntimeTool(name="norns_update_card", openai_tool={}, execute=execute)]

    queued: list[tuple[str, str]] = []

    async def fake_enqueue(card_id: str, stage_id: str, run_id: str | None = None):
        queued.append((card_id, stage_id))
        return run_id or "queued"

    monkeypatch.setattr("backend.app.tools.registry.create_default_registry", FakeRegistry)
    monkeypatch.setattr("backend.app.orchestrator.gates.enqueue_stage_run", fake_enqueue)

    async with SessionLocal() as session:
        board = Board(name="Board")
        stage = Stage(name="Urd", order=1, require_approval=True, confirm_writes=True)
        stage.agent_config = AgentConfig(system_prompt="urd", model="gpt-4o", temperature=0.7, tool_allowlist=["norns"])
        board.stages = [stage]
        card = Card(title="Card", body="Body", status=CardStatus.WAITING_TOOL_APPROVAL, current_stage=stage)
        board.cards = [card]
        run = AgentRun(
            card=card,
            stage=stage,
            inputs={
                "workspace": {"path": "/tmp/app", "git_url": "https://github.com/acme/app", "github_repo": "acme/app"},
                "pending_writes": [{"name": "norns_update_card", "arguments": {"title": "Renamed"}}],
            },
            tool_calls=[],
            model_output="queued write",
            handoff={"summary": "queued write"},
            status="waiting_tool",
        )
        session.add_all([board, run])
        await session.commit()

        approval = await approve_pending_writes(session, card.id, "admin")
        await session.refresh(card)
        await session.refresh(run)
        assert approval.approved is True
        assert isinstance(seen["context"], PluginContext)
        context = seen["context"]
        assert context.card_id == card.id
        assert context.board_id == board.id
        assert context.stage_id == stage.id
        assert context.workspace_path == "/tmp/app"
        assert context.github_repo == "acme/app"
        assert seen["arguments"]["card_id"] == card.id
        assert seen["arguments"]["title"] == "Renamed"
        assert run.inputs["pending_writes"] == []
        assert run.status == "completed"
        assert card.status == CardStatus.RUNNING
        assert queued == [(card.id, stage.id)]

    await engine.dispose()


@pytest.mark.asyncio
async def test_approve_pending_writes_stops_after_first_error(monkeypatch):
    engine, SessionLocal = await _session_factory()
    calls: list[str] = []

    class FakeRegistry:
        def get_runtime_tools(self, allowlist, connectors, context=None):
            del allowlist, connectors, context

            async def ok(arguments: dict) -> dict:
                del arguments
                calls.append("ok")
                return {"ok": True}

            async def boom(arguments: dict) -> dict:
                del arguments
                calls.append("boom")
                return {"error": "jira 400"}

            return [
                RuntimeTool(name="norns_update_card", openai_tool={}, execute=ok),
                RuntimeTool(name="jira_jira_create_issue", openai_tool={}, execute=boom),
            ]

    monkeypatch.setattr("backend.app.tools.registry.create_default_registry", FakeRegistry)

    async with SessionLocal() as session:
        board = Board(name="Board")
        stage = Stage(name="Urd", order=1, require_approval=True, confirm_writes=True)
        stage.agent_config = AgentConfig(
            system_prompt="urd", model="gpt-4o", temperature=0.7, tool_allowlist=["norns", "jira"]
        )
        board.stages = [stage]
        card = Card(title="Card", body="Body", status=CardStatus.WAITING_TOOL_APPROVAL, current_stage=stage)
        board.cards = [card]
        run = AgentRun(
            card=card,
            stage=stage,
            inputs={
                "pending_writes": [
                    {"name": "norns_update_card", "arguments": {"title": "A"}},
                    {"name": "jira_jira_create_issue", "arguments": {"summary": "B"}},
                    {"name": "norns_update_card", "arguments": {"title": "C"}},
                ]
            },
            tool_calls=[],
            model_output="queued",
            handoff={"summary": "queued"},
            status="waiting_tool",
        )
        session.add_all([board, run])
        await session.commit()

        with pytest.raises(ValueError, match="jira_jira_create_issue failed"):
            await approve_pending_writes(session, card.id, "admin")
        await session.refresh(card)
        await session.refresh(run)
        assert calls == ["ok", "boom"]
        assert card.status == CardStatus.WAITING_TOOL_APPROVAL
        assert run.status == "waiting_tool"
        remaining = run.inputs["pending_writes"]
        assert remaining[0]["name"] == "jira_jira_create_issue"
        assert remaining[0]["status"] == "failed"
        assert remaining[1]["name"] == "norns_update_card"
        assert run.inputs["confirmed_writes"][0]["name"] == "norns_update_card"

    await engine.dispose()


@pytest.mark.asyncio
async def test_approve_pending_writes_keeps_existing_external_id(monkeypatch):
    engine, SessionLocal = await _session_factory()

    class FakeRegistry:
        def get_runtime_tools(self, allowlist, connectors, context=None):
            del allowlist, connectors, context

            async def create_issue(arguments: dict) -> dict:
                del arguments
                return {"key": "NOR-99"}

            return [RuntimeTool(name="jira_jira_create_issue", openai_tool={}, execute=create_issue)]

    async def fake_enqueue(card_id: str, stage_id: str, run_id: str | None = None):
        del card_id, stage_id
        return run_id or "queued"

    monkeypatch.setattr("backend.app.tools.registry.create_default_registry", FakeRegistry)
    monkeypatch.setattr("backend.app.orchestrator.gates.enqueue_stage_run", fake_enqueue)

    async with SessionLocal() as session:
        board = Board(name="Board")
        stage = Stage(name="Urd", order=1, require_approval=True, confirm_writes=True)
        stage.agent_config = AgentConfig(system_prompt="urd", model="gpt-4o", temperature=0.7, tool_allowlist=["jira"])
        board.stages = [stage]
        card = Card(
            title="Software requirements",
            body="Polarion section",
            status=CardStatus.WAITING_TOOL_APPROVAL,
            current_stage=stage,
            external_id="5E96-147",
        )
        board.cards = [card]
        run = AgentRun(
            card=card,
            stage=stage,
            inputs={"pending_writes": [{"name": "jira_jira_create_issue", "arguments": {"summary": "Define SWR"}}]},
            tool_calls=[],
            model_output="queued write",
            handoff={"summary": "queued write"},
            status="waiting_tool",
        )
        session.add_all([board, run])
        await session.commit()

        approval = await approve_pending_writes(session, card.id, "admin")
        await session.refresh(card)
        assert approval.approved is True
        assert card.external_id == "5E96-147"

    await engine.dispose()


@pytest.mark.asyncio
async def test_reject_pending_writes_cleans_sandbox(monkeypatch):
    engine, SessionLocal = await _session_factory()
    cleaned: list[dict] = []

    def fake_cleanup(payload):
        cleaned.append(dict(payload or {}))

    monkeypatch.setattr("backend.app.orchestrator.gates.cleanup_serialized_sandbox", fake_cleanup)

    async with SessionLocal() as session:
        board = Board(name="Board")
        stage = Stage(name="Urd", order=1, require_approval=True, confirm_writes=True)
        stage.agent_config = AgentConfig(system_prompt="x", model="gpt", temperature=0.1, tool_allowlist=["norns"])
        board.stages = [stage]
        card = Card(title="Card", body="Body", board=board, current_stage=stage, status=CardStatus.WAITING_TOOL_APPROVAL)
        board.cards = [card]
        run = AgentRun(
            card=card,
            stage=stage,
            inputs={
                "pending_writes": [{"name": "norns_update_card", "arguments": {"title": "Nope"}}],
                "sandbox": {"backend": "docker", "path": "/tmp/sb", "metadata": {"container_id": "cid"}},
            },
            tool_calls=[],
            model_output="queued",
            handoff={"summary": "queued"},
            status="waiting_tool",
        )
        session.add_all([board, run])
        await session.commit()

        approval = await reject_pending_writes(session, card.id, "admin")
        assert approval.approved is False
        assert cleaned and cleaned[0]["path"] == "/tmp/sb"

    await engine.dispose()
