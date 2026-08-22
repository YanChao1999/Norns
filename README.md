# Norns

Norns is a Kanban orchestration system where each board column runs an isolated LLM agent and a human approval gate controls progression to the next stage. The name comes from the Norse Norns: Urd, Verdandi, and Skuld.

## Features
- FastAPI + async SQLAlchemy backend with PostgreSQL-ready configuration
- ARQ/Redis queue for isolated stage execution
- React + TypeScript Kanban UI with approval-aware movement
- Encrypted connector secrets at rest with Fernet
- OpenAI-compatible stage agents with explicit per-stage tool allowlists
- PlantUML-first documentation and handoff previews

## Flow Diagram
```plantuml
@startuml
skinparam monochrome true
actor Human
rectangle Board {
  rectangle "Stage 1\n(Urd agent)" as S1
  rectangle "Stage 2\n(Verdandi agent)" as S2
  rectangle "Stage 3\n(Skuld agent)" as S3
}
Human --> S1 : create / approve
S1 --> Human : handoff
Human --> S2 : approve advance
S2 --> Human : handoff
Human --> S3 : approve advance
@enduml
```

## Runtime Sequence
```plantuml
@startuml
skinparam monochrome true
actor Human
participant Frontend
participant Backend
participant Redis
participant Worker
participant Agent

Human -> Frontend : Approve card
Frontend -> Backend : POST /api/cards/{id}/approve
Backend -> Redis : enqueue next stage
Redis -> Worker : run_stage_task
Worker -> Agent : run_stage(card, stage, run)
Agent -> Backend : persist AgentRun + handoff
Backend -> Frontend : waiting_approval state
@enduml
```

## Architecture Overview
- **Boards / Stages** define the workflow and per-column agent configuration.
- **Cards** carry the work item body and current stage pointer.
- **Agent runs** are isolated; no chat memory is shared between stages.
- **Handoffs** from stage _N_ are the only structured context for stage _N+1_.
- **Connectors** are Python-library backed only (PyGithub, jira, polarion); raw credentials are never exposed to agents.

## Quick Start
1. Copy `.env.example` to `.env` and set real secrets.
2. Generate a unique encryption key (do not keep the example value):
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
   Put the result in `ENCRYPTION_KEY`. The API and worker must share the same key.
3. Start the stack:
   ```bash
   docker compose up
   ```
4. Open:
   - Frontend: `http://localhost:5173`
   - Backend API: `http://localhost:8000/docs`
5. Sign in with the `ADMIN_USERNAME` / `ADMIN_PASSWORD` from your `.env` (defaults are `admin` / `admin`).
6. Create a board, add a card, open it, and click **Run this stage**. Cards only move after approval unless a stage has auto-advance enabled.

## Development Setup
```bash
pip install -e ".[dev]"
python -m pytest backend/tests/ -q
cd frontend && npm install && npm run dev
```

## Notes
- Use PostgreSQL in normal deployments via `DATABASE_URL`.
- Redis backs ARQ worker execution.
- PlantUML diagrams are rendered through Kroki with a graceful SVG fallback.
- An empty per-stage tool allowlist grants **no** tools. Enable GitHub, Jira, or Polarion explicitly on the stage.
- `PUT /api/cards/{id}` updates title/body only; stage movement goes through run + approval (or auto-advance).
