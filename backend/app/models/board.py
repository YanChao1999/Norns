from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class Board(Base):
    __tablename__ = "boards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    workspace_path: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    git_url: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)

    stages: Mapped[list[Stage]] = relationship(
        back_populates="board",
        cascade="all, delete-orphan",
        order_by="Stage.order",
    )
    transitions: Mapped[list[StageTransition]] = relationship(
        back_populates="board",
        cascade="all, delete-orphan",
    )
    cards: Mapped[list[Card]] = relationship(back_populates="board", cascade="all, delete-orphan")


class Stage(Base):
    __tablename__ = "stages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    board_id: Mapped[str] = mapped_column(ForeignKey("boards.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    lane: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    require_approval: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    confirm_writes: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auto_start: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    board: Mapped[Board] = relationship(back_populates="stages")
    agent_config: Mapped[AgentConfig | None] = relationship(
        back_populates="stage",
        cascade="all, delete-orphan",
        uselist=False,
    )
    cards: Mapped[list[Card]] = relationship(back_populates="current_stage")


class AgentConfig(Base):
    __tablename__ = "agent_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    stage_id: Mapped[str] = mapped_column(ForeignKey("stages.id", ondelete="CASCADE"), unique=True, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, default="You are the stage agent.", nullable=False)
    model: Mapped[str] = mapped_column(String(120), default="gpt-4o", nullable=False)
    llm_provider: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    temperature: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    tool_allowlist: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    workspace_path: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    git_url: Mapped[str] = mapped_column(String(1024), default="", nullable=False)

    stage: Mapped[Stage] = relationship(back_populates="agent_config")


class StageTransition(Base):
    __tablename__ = "stage_transitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    board_id: Mapped[str] = mapped_column(ForeignKey("boards.id", ondelete="CASCADE"), nullable=False)
    from_stage_id: Mapped[str] = mapped_column(ForeignKey("stages.id", ondelete="CASCADE"), nullable=False)
    to_stage_id: Mapped[str | None] = mapped_column(ForeignKey("stages.id", ondelete="CASCADE"), nullable=True)
    event: Mapped[str] = mapped_column(String(32), default="approve", nullable=False)
    condition_key: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    condition_op: Mapped[str] = mapped_column(String(32), default="eq", nullable=False)
    condition_value: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    board: Mapped[Board] = relationship(back_populates="transitions")
    from_stage: Mapped[Stage] = relationship(foreign_keys=[from_stage_id])
    to_stage: Mapped[Stage | None] = relationship(foreign_keys=[to_stage_id])


from .card import Card  # noqa: E402
