from __future__ import annotations

import asyncio
from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import backend.app.orchestrator.enqueue as enqueue
from backend.app.config import get_settings
from backend.app.database import Base
from backend.app.models import AgentConfig, AgentRun, Board, Card, Stage, StageTransition
from backend.app.orchestrator.gates import approve_card, reject_card
from backend.app.orchestrator.state_machine import CardStatus


@pytest.mark.asyncio
async def test_enqueue_stage_run_uses_arq(monkeypatch):
    captured: dict[str, object] = {}

    class FakeRedis:
        async def enqueue_job(self, name, **kwargs):
            captured["name"] = name
            captured["kwargs"] = kwargs

        async def close(self):
            captured["closed"] = True

    async def fake_create_pool(_settings):
        captured["pool"] = True
        return FakeRedis()

    monkeypatch.setattr(enqueue, "create_pool", fake_create_pool)
    monkeypatch.setattr(enqueue, "_pool", None)

    run_id = await enqueue.enqueue_stage_run("card-1", "stage-1", "run-1")
    assert run_id == "run-1"
    assert captured["name"] == "run_stage_task"
    assert captured["kwargs"] == {"card_id": "card-1", "stage_id": "stage-1", "run_id": "run-1"}
    assert captured["pool"] is True


@pytest.mark.asyncio
async def test_enqueue_stage_run_inline(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_run_stage(card_id, stage_id, run_id):
        captured["args"] = (card_id, stage_id, run_id)

    monkeypatch.setenv("QUEUE_BACKEND", "inline")
    get_settings.cache_clear()
    monkeypatch.setattr("backend.app.agents.runner.run_stage", fake_run_stage)
    try:
        run_id = await enqueue.enqueue_stage_run("card-1", "stage-1", "run-inline")
        pending = list(enqueue._inline_tasks)
        if pending:
            await asyncio.gather(*pending)
        assert run_id == "run-inline"
        assert captured["args"] == ("card-1", "stage-1", "run-inline")
        assert not enqueue._inline_tasks
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_gate_logic_creates_approval_and_moves_card(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    queued: list[tuple[str, str]] = []

    async def fake_enqueue(card_id: str, stage_id: str, run_id: str | None = None):
        queued.append((card_id, stage_id))
        return run_id or "generated-run"

    monkeypatch.setattr("backend.app.orchestrator.gates.enqueue_stage_run", fake_enqueue)

    async with SessionLocal() as session:
        board = Board(name="Board")
        stage_a = Stage(name="Todo", order=1, require_approval=True)
        stage_a.agent_config = AgentConfig(system_prompt="todo", model="gpt-4o", temperature=0.7, tool_allowlist=[])
        stage_b = Stage(name="Doing", order=2, require_approval=True)
        stage_b.agent_config = AgentConfig(system_prompt="doing", model="gpt-4o", temperature=0.7, tool_allowlist=[])
        board.stages = [stage_a, stage_b]
        card = Card(title="Card", body="Body", status=CardStatus.WAITING_APPROVAL, current_stage=stage_a)
        board.cards = [card]
        run = AgentRun(
            card=card,
            stage=stage_a,
            inputs={},
            tool_calls=[],
            model_output="done",
            handoff={"summary": "handoff"},
            status="completed",
            completed_at=datetime.utcnow(),
        )
        session.add_all([board, run])
        await session.commit()

        approval = await approve_card(session, card.id, "admin", "looks good")
        await session.refresh(card)
        assert approval.approved is True
        assert card.current_stage_id == stage_b.id
        assert card.status == CardStatus.RUNNING
        assert queued == [(card.id, stage_b.id)]

        card.status = CardStatus.WAITING_APPROVAL
        run2 = AgentRun(
            card_id=card.id,
            stage_id=stage_b.id,
            inputs={},
            tool_calls=[],
            model_output="retry",
            handoff={"summary": "redo"},
            status="completed",
            completed_at=datetime.utcnow(),
        )
        session.add(run2)
        await session.commit()

        rejection = await reject_card(session, card.id, "admin", "needs work")
        await session.refresh(card)
        assert rejection.approved is False
        assert card.current_stage_id == stage_b.id
        assert card.status == CardStatus.BLOCKED

    await engine.dispose()


@pytest.mark.asyncio
async def test_reject_line_returns_card_to_previous_stage():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        board = Board(name="Board")
        stage_a = Stage(name="Todo", order=1, require_approval=True)
        stage_a.agent_config = AgentConfig(system_prompt="todo", model="gpt-4o", temperature=0.7, tool_allowlist=[])
        stage_b = Stage(name="Doing", order=2, require_approval=True)
        stage_b.agent_config = AgentConfig(system_prompt="doing", model="gpt-4o", temperature=0.7, tool_allowlist=[])
        board.stages = [stage_a, stage_b]
        card = Card(title="Card", body="Body", status=CardStatus.WAITING_APPROVAL, current_stage=stage_b)
        board.cards = [card]
        run = AgentRun(
            card=card,
            stage=stage_b,
            inputs={},
            tool_calls=[],
            model_output="done",
            handoff={"summary": "handoff"},
            status="completed",
            completed_at=datetime.utcnow(),
        )
        session.add_all([board, run])
        await session.flush()
        session.add(
            StageTransition(
                board_id=board.id,
                from_stage_id=stage_b.id,
                to_stage_id=stage_a.id,
                event="reject",
            )
        )
        await session.commit()

        await reject_card(session, card.id, "admin", "send back")
        await session.refresh(card)
        assert card.current_stage_id == stage_a.id
        assert card.status == CardStatus.IDLE

    await engine.dispose()


def _agent_stage(name: str, order: int, lane: int = 0) -> Stage:
    stage = Stage(name=name, order=order, lane=lane, require_approval=True)
    stage.agent_config = AgentConfig(system_prompt=name, model="gpt-4o", temperature=0.7, tool_allowlist=[])
    return stage


def _completed_run(card: Card, stage: Stage, summary: str) -> AgentRun:
    return AgentRun(
        card=card,
        stage=stage,
        inputs={},
        tool_calls=[],
        model_output=summary,
        handoff={"summary": summary},
        status="completed",
        completed_at=datetime.utcnow(),
    )


@pytest.mark.asyncio
async def test_approve_forks_parallel_tracks(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    queued: list[tuple[str, str]] = []

    async def fake_enqueue(card_id: str, stage_id: str, run_id: str | None = None):
        queued.append((card_id, stage_id))
        return run_id or "generated-run"

    monkeypatch.setattr("backend.app.orchestrator.gates.enqueue_stage_run", fake_enqueue)

    async with SessionLocal() as session:
        board = Board(name="Board")
        interface = _agent_stage("Interface", 1)
        tests = _agent_stage("Unit tests", 2, 0)
        software = _agent_stage("Software", 2, 1)
        board.stages = [interface, tests, software]
        card = Card(title="API", body="Ship it", status=CardStatus.WAITING_APPROVAL, current_stage=interface)
        board.cards = [card]
        session.add_all([board, _completed_run(card, interface, "interface ready")])
        await session.flush()
        session.add_all(
            [
                StageTransition(
                    board_id=board.id,
                    from_stage_id=interface.id,
                    to_stage_id=tests.id,
                    event="approve",
                    order=0,
                ),
                StageTransition(
                    board_id=board.id,
                    from_stage_id=interface.id,
                    to_stage_id=software.id,
                    event="approve",
                    order=1,
                ),
            ]
        )
        await session.commit()

        await approve_card(session, card.id, "admin", "split")
        await session.refresh(card)
        children = list((await session.execute(select(Card).where(Card.parent_card_id == card.id))).scalars().all())
        assert card.current_stage_id == tests.id
        assert card.status == CardStatus.RUNNING
        assert len(children) == 1
        assert children[0].current_stage_id == software.id
        assert children[0].status == CardStatus.RUNNING
        assert children[0].title == "API · Software"
        assert {(item[0], item[1]) for item in queued} == {(card.id, tests.id), (children[0].id, software.id)}

    await engine.dispose()


@pytest.mark.asyncio
async def test_nested_split_stays_attached_to_root(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    queued: list[tuple[str, str]] = []

    async def fake_enqueue(card_id: str, stage_id: str, run_id: str | None = None):
        queued.append((card_id, stage_id))
        return run_id or "generated-run"

    monkeypatch.setattr("backend.app.orchestrator.gates.enqueue_stage_run", fake_enqueue)

    async with SessionLocal() as session:
        board = Board(name="Board")
        interface = _agent_stage("Interface", 1)
        tests = _agent_stage("Unit tests", 2, 0)
        software = _agent_stage("Software", 2, 1)
        lint = _agent_stage("Lint", 3, 0)
        types = _agent_stage("Types", 3, 1)
        board.stages = [interface, tests, software, lint, types]
        parent = Card(title="API", body="Ship it", status=CardStatus.WAITING_APPROVAL, current_stage=software)
        child = Card(
            title="API · Software",
            body="Ship it",
            status=CardStatus.WAITING_APPROVAL,
            current_stage=software,
            parent_card_id="pending",
        )
        board.cards = [parent, child]
        session.add(board)
        await session.flush()
        child.parent_card_id = parent.id
        session.add_all(
            [
                _completed_run(child, software, "software ready"),
                StageTransition(
                    board_id=board.id, from_stage_id=software.id, to_stage_id=lint.id, event="approve", order=0
                ),
                StageTransition(
                    board_id=board.id, from_stage_id=software.id, to_stage_id=types.id, event="approve", order=1
                ),
            ]
        )
        await session.commit()

        await approve_card(session, child.id, "admin", "split again")
        grandchildren = list(
            (await session.execute(select(Card).where(Card.id != child.id, Card.id != parent.id))).scalars().all()
        )
        assert len(grandchildren) == 1
        assert grandchildren[0].parent_card_id == parent.id
        assert grandchildren[0].current_stage_id == types.id
        await session.refresh(child)
        assert child.current_stage_id == lint.id
        family = list(
            (await session.execute(select(Card).where((Card.id == parent.id) | (Card.parent_card_id == parent.id))))
            .scalars()
            .all()
        )
        assert {item.id for item in family} == {parent.id, child.id, grandchildren[0].id}

    await engine.dispose()


@pytest.mark.asyncio
async def test_join_stage_runs_independently_without_wait(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    queued: list[tuple[str, str]] = []

    async def fake_enqueue(card_id: str, stage_id: str, run_id: str | None = None):
        queued.append((card_id, stage_id))
        return run_id or "generated-run"

    monkeypatch.setattr("backend.app.orchestrator.gates.enqueue_stage_run", fake_enqueue)

    async with SessionLocal() as session:
        board = Board(name="Board")
        interface = _agent_stage("Interface", 1)
        tests = _agent_stage("Unit tests", 2, 0)
        software = _agent_stage("Software", 2, 1)
        integration = _agent_stage("Integration", 3)
        board.stages = [interface, tests, software, integration]
        parent = Card(title="API", body="Ship it", status=CardStatus.WAITING_APPROVAL, current_stage=tests)
        child = Card(
            title="API · Software",
            body="Ship it",
            status=CardStatus.WAITING_APPROVAL,
            current_stage=software,
            parent_card_id="pending",
        )
        board.cards = [parent, child]
        session.add(board)
        await session.flush()
        child.parent_card_id = parent.id
        session.add_all(
            [
                _completed_run(parent, tests, "tests green"),
                _completed_run(child, software, "software ready"),
                StageTransition(board_id=board.id, from_stage_id=tests.id, to_stage_id=integration.id, event="approve"),
                StageTransition(
                    board_id=board.id, from_stage_id=software.id, to_stage_id=integration.id, event="approve"
                ),
            ]
        )
        await session.commit()

        queued.clear()
        await approve_card(session, parent.id, "admin", "tests done")
        await session.refresh(parent)
        await session.refresh(child)
        assert parent.current_stage_id == integration.id
        assert parent.status == CardStatus.RUNNING
        assert child.current_stage_id == software.id
        assert child.status == CardStatus.WAITING_APPROVAL
        assert queued == [(parent.id, integration.id)]

        queued.clear()
        await approve_card(session, child.id, "admin", "software done")
        await session.refresh(parent)
        await session.refresh(child)
        assert parent.current_stage_id == integration.id
        assert parent.status == CardStatus.RUNNING
        assert child.current_stage_id == integration.id
        assert child.status == CardStatus.RUNNING
        assert queued == [(child.id, integration.id)]
        joined = list(
            (
                await session.execute(
                    select(AgentRun).where(AgentRun.model_output == "Joined parallel tracks.")
                )
            )
            .scalars()
            .all()
        )
        assert joined == []

    await engine.dispose()


@pytest.mark.asyncio
async def test_approve_uses_planned_tracks_for_fork_bodies(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    queued: list[tuple[str, str]] = []

    async def fake_enqueue(card_id: str, stage_id: str, run_id: str | None = None):
        queued.append((card_id, stage_id))
        return run_id or "generated-run"

    monkeypatch.setattr("backend.app.orchestrator.gates.enqueue_stage_run", fake_enqueue)

    async with SessionLocal() as session:
        board = Board(name="Board")
        interface = _agent_stage("Interface", 1)
        tests = _agent_stage("Unit tests", 2, 0)
        software = _agent_stage("Software", 2, 1)
        board.stages = [interface, tests, software]
        card = Card(title="API", body="Ship it", status=CardStatus.WAITING_APPROVAL, current_stage=interface)
        board.cards = [card]
        session.add(board)
        await session.flush()
        run = _completed_run(card, interface, "interface ready")
        run.handoff = {
            "summary": "Split the work",
            "tracks": [
                {
                    "stage_id": tests.id,
                    "title": "API tests",
                    "body": "Write unit tests",
                    "summary": "tests track",
                },
                {
                    "stage_id": software.id,
                    "title": "API impl",
                    "body": "Implement handlers",
                    "summary": "software track",
                },
            ],
        }
        session.add(run)
        session.add_all(
            [
                StageTransition(
                    board_id=board.id,
                    from_stage_id=interface.id,
                    to_stage_id=tests.id,
                    event="approve",
                    order=0,
                ),
                StageTransition(
                    board_id=board.id,
                    from_stage_id=interface.id,
                    to_stage_id=software.id,
                    event="approve",
                    order=1,
                ),
            ]
        )
        await session.commit()

        await approve_card(session, card.id, "admin", "split")
        await session.refresh(card)
        children = list((await session.execute(select(Card).where(Card.parent_card_id == card.id))).scalars().all())
        assert card.title == "API tests"
        assert card.body == "Write unit tests"
        assert card.current_stage_id == tests.id
        assert len(children) == 1
        assert children[0].title == "API impl"
        assert children[0].body == "Implement handlers"
        assert children[0].current_stage_id == software.id
        assert {(item[0], item[1]) for item in queued} == {(card.id, tests.id), (children[0].id, software.id)}

    await engine.dispose()


@pytest.mark.asyncio
async def test_approve_falls_back_when_track_plan_length_mismatches(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def fake_enqueue(card_id: str, stage_id: str, run_id: str | None = None):
        return run_id or "generated-run"

    monkeypatch.setattr("backend.app.orchestrator.gates.enqueue_stage_run", fake_enqueue)

    async with SessionLocal() as session:
        board = Board(name="Board")
        interface = _agent_stage("Interface", 1)
        tests = _agent_stage("Unit tests", 2, 0)
        software = _agent_stage("Software", 2, 1)
        board.stages = [interface, tests, software]
        card = Card(title="API", body="Ship it", status=CardStatus.WAITING_APPROVAL, current_stage=interface)
        board.cards = [card]
        run = _completed_run(card, interface, "interface ready")
        run.handoff = {"summary": "bad plan", "tracks": [{"title": "only one", "body": "x"}]}
        session.add_all([board, run])
        await session.flush()
        session.add_all(
            [
                StageTransition(
                    board_id=board.id,
                    from_stage_id=interface.id,
                    to_stage_id=tests.id,
                    event="approve",
                    order=0,
                ),
                StageTransition(
                    board_id=board.id,
                    from_stage_id=interface.id,
                    to_stage_id=software.id,
                    event="approve",
                    order=1,
                ),
            ]
        )
        await session.commit()

        await approve_card(session, card.id, "admin", "split")
        await session.refresh(card)
        children = list((await session.execute(select(Card).where(Card.parent_card_id == card.id))).scalars().all())
        assert card.title == "API"
        assert card.body == "Ship it"
        assert children[0].title == "API · Software"
        assert children[0].body == "Ship it"

    await engine.dispose()
