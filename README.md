# Norns

Agents work the columns. You decide what moves. Kanban orchestration with human gates.

Named after Urd, Verdandi, and Skuld.

[![CI](https://github.com/YanChao1999/Norns/actions/workflows/tests.yml/badge.svg)](https://github.com/YanChao1999/Norns/actions/workflows/tests.yml)
[![PyPI](https://img.shields.io/pypi/v/norns-ide.svg)](https://pypi.org/project/norns-ide/)
[![Downloads](https://img.shields.io/pypi/dm/norns-ide.svg)](https://pepy.tech/projects/norns-ide)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-pytest-green.svg)](https://github.com/YanChao1999/Norns/actions/workflows/tests.yml)
[![Coverage](https://img.shields.io/badge/coverage-pytest--cov-informational.svg)](https://github.com/YanChao1999/Norns/blob/main/pyproject.toml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/github/license/YanChao1999/Norns.svg)](LICENSE)

**v0.0.2** · Site: [yanchao1999.github.io/Norns](https://yanchao1999.github.io/Norns/) · Backlog: [ROADMAP.md](ROADMAP.md)

## Downloads

![norns-ide PyPI downloads trend](assets/downloads-trend.svg)

## Install

Python 3.12+. The command is `norns`; the package is `norns-ide` (`norns` is taken on PyPI).

```bash
uv tool install norns-ide
# or
python3 -m pip install norns-ide

norns init    # prints an admin password; also stored in ~/.norns/config.toml
norns run     # http://127.0.0.1:8765
```

From this checkout (needs Node.js 20+ or Docker once, to compile the UI):

```bash
uv tool install .
norns init && norns run
uv sync --extra dev && uv run pre-commit install   # format, lint, tests on commit
```

`norns run --no-window` starts the server without a browser. Data lives under `~/.norns` (`--home` / `NORNS_HOME`). `norns init --force` replaces config and deletes `norns.db`. Publishing: [PUBLISH.md](PUBLISH.md).

### First run

1. Log in as `admin` with the password from `norns init`.
2. If there are no boards, the Control Room shows a short checklist and a **Settings** CTA.
3. Create a board (includes a sample card), add DeepSeek / OpenAI / Cursor in Settings, optionally **Bind git**, then **Run** the sample card.
4. Without a usable model key you stay in **practice mode** (banner + practice gate labels). Fake keys do not clear that banner — health probes the provider model list.

## Features

- Local Control Room in the browser (`norns init` / `norns run`); optional Electron window
- Visual machine editor: stages, parallel tracks, human gates vs auto-advance
- Isolated per-stage agents (no shared chat memory); human confirms approve/reject
- Encrypted connectors (OpenAI, Cursor, DeepSeek, GitHub, Jira, Polarion)
- Live Cursor model catalog for Agent selection; wait UI counts down to Cursor timeout
- Per-column tool allowlists (Norns, sandbox, GitHub, Jira, Polarion, extra MCP)
- Directory or hardened Docker sandbox copies under `~/.norns/sandboxes/`
- SQLite + in-process queue locally; PostgreSQL + Redis/ARQ when you need them

```plantuml
@startuml
skinparam monochrome true
actor Human
rectangle Board {
  rectangle "Stage 1" as S1
  rectangle "Stage 2" as S2
  rectangle "Stage 3" as S3
}
Human --> S1 : create / approve
S1 --> Human : handoff + recommend
Human --> S2 : confirm
S2 --> Human : handoff + recommend
Human --> S3 : confirm
@enduml
```

## How it works

- **Boards / stages** — workflow and per-column agents. Two default lines from a stage **split** a card (`handoff.tracks`). Later columns (Review, Merge, …) are a **soft join**: each fork arrives and runs on its own. **Auto-start idle cards** on a column until a human gate (or write confirm) stops it.
- **Sandbox** — local workspace runs copy under `~/.norns/sandboxes/` (`directory`, hardened `docker`, or `none`). Host/Cursor file tools use the bind-mounted copy path; **command** isolation for `docker` is via the **sandbox** plugin (`sandbox_run` → docker exec). Allowlist **sandbox** for reproduce / env-build. Set `[sandbox] backend` in `~/.norns/config.toml`.
- **Handoffs** — the only structured context for the next stage. On a gate, `recommendation` is advisory until a person confirms. Practice runs are labeled and do not auto-advance to `done` without a real model.
- **Git bind** — each board has a checkout path and/or git URL (path must exist; URL must look like a remote). Stage agents inherit the board repo unless the column **Agent** overrides it. `GET /api/workspace?board_id=` reflects that binding.
- **Connectors** — Python libraries only; agents never see raw credentials. Empty tool allowlist means no tools. Failed stage runs leave the card **blocked** (same as reject).

Optional stack (Postgres, Redis, Vite): copy `.env.example` → `.env`, then `docker compose up` → UI at `http://localhost:5173`.
