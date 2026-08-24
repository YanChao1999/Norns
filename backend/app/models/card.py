from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from ..orchestrator.state_machine import CardStatus


class Card(Base):
    __tablename__ = "cards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    board_id: Mapped[str] = mapped_column(ForeignKey("boards.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    current_stage_id: Mapped[str | None] = mapped_column(ForeignKey("stages.id", ondelete="SET NULL"), nullable=True)
    parent_card_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[CardStatus] = mapped_column(
        Enum(CardStatus, name="card_status", native_enum=False),
        default=CardStatus.IDLE,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)

    board: Mapped[Board] = relationship(back_populates="cards")
    current_stage: Mapped[Stage | None] = relationship(back_populates="cards")
    runs: Mapped[list[AgentRun]] = relationship(back_populates="card", cascade="all, delete-orphan")
    approvals: Mapped[list[Approval]] = relationship(back_populates="card", cascade="all, delete-orphan")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    card_id: Mapped[str] = mapped_column(ForeignKey("cards.id", ondelete="CASCADE"), nullable=False)
    stage_id: Mapped[str] = mapped_column(ForeignKey("stages.id", ondelete="CASCADE"), nullable=False)
    inputs: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    tool_calls: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    model_output: Mapped[str] = mapped_column(Text, default="", nullable=False)
    handoff: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)

    card: Mapped[Card] = relationship(back_populates="runs")
    stage: Mapped[Stage] = relationship()
    approvals: Mapped[list[Approval]] = relationship(back_populates="agent_run")


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    card_id: Mapped[str] = mapped_column(ForeignKey("cards.id", ondelete="CASCADE"), nullable=False)
    stage_id: Mapped[str] = mapped_column(ForeignKey("stages.id", ondelete="CASCADE"), nullable=False)
    agent_run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    approved: Mapped[bool] = mapped_column(nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    card: Mapped[Card] = relationship(back_populates="approvals")
    agent_run: Mapped[AgentRun] = relationship(back_populates="approvals")
    stage: Mapped[Stage] = relationship()


from .board import Board, Stage  # noqa: E402
