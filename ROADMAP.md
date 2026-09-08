# Roadmap

Shipped on `main`: 0.0.1 Control Room loop (boards, Machine editor, human gates, parallel split/join, local `norns init` / `norns run`).

This file is the first-use backlog. **Now:** pip / uv install (`feat/pip-uv-install`). Everything else stays here until it has its own branch.

## Now

- [x] **pip / uv install** — `uv tool install .` / `pip install .` on `feat/pip-uv-install`. CI checks the wheel, sdist, `twine`, packaged UI, and `/api/health` plus the Control Room HTML.
- [ ] **Publish 0.0.1 to PyPI as `norns-ide`** — `norns` is taken on PyPI. Follow [PUBLISH.md](PUBLISH.md): TestPyPI first (`workflow_dispatch`), then PyPI (trusted publisher / GitHub Release). Install with `pip install norns-ide` or `uv tool install norns-ide`.
- [ ] **Parallel planned split + sandbox** (`feat/parallel-planned-split-sandbox`) — soft join (no wait/merge); previous column plans `handoff.tracks`; directory or Docker sandbox per agent run; microVM / gVisor reserved.

## First-use Settings (users cannot finish setup in the UI)

- [x] **Connector form in Settings** — add/edit/disable OpenAI, Cursor, DeepSeek, Jira, GitHub, Polarion. OpenAI / Cursor / DeepSeek are model connectors (`api_key`, optional `base_url` / `default_model`). Jira needs `server`, `username`, `token`. GitHub needs `token` (optional `base_url`). Polarion needs `server`, `username`, `password`, optional `project`.
- [x] **API key in Settings** — OpenAI-compatible keys are encrypted connectors (OpenAI, Cursor, DeepSeek). Env/`config.toml` still works as a fallback.
- [x] **Agent setup path** — explain that the column **Agent** button opens prompt / model / tools; an empty tool allowlist grants no tools; checking `norns` / `sandbox` / `jira` / `github` / `polarion` (or an MCP connector) attaches those plugins. Cursor stages get MCP; OpenAI-compatible stages get function tools.
- [ ] **Warn when tools have no connector** — do not silently grant nothing.
- [ ] **Empty state after login** — with no boards, land in Settings (or a short checklist): create board → API key → connector if you need tools → open the board.
- [ ] **Login copy** — username is `admin`; password was printed by `norns init` and is in `~/.norns/config.toml`.

## Docs / install leftovers

- [x] **Pages install snippet** — `docs/index.html` install path is PyPI / TestPyPI `norns-ide` for 0.0.2 (checkout `uv tool install .` remains as a fallback).
- [ ] **Sample board / card** — optional seeded work so the first session is not an empty board.

## After first use / publish

- [x] **Hardened Docker sandbox** — only the sandbox copy bind-mounted, `--cap-drop ALL`, read-only rootfs, no-new-privileges, tmpfs for scratch (`sandbox.backend = "docker"`). Host-side agent tools still see the copy path; containerized `run_in_sandbox` is the hard jail.
- [x] **Sandbox MCP plugin** — allowlist `sandbox` for `sandbox_info` / `sandbox_run` / list-read-write / `sandbox_copy_in` so agents can reproduce issues and build envs inside the per-run copy (docker exec when hardened Docker is active).
- [ ] **Sandbox microVM backend** — stronger isolation when containers are not enough (`sandbox.backend = "microvm"`). Prefer hardened `docker` until then.
- [ ] **gVisor + agent runtime policy** — user-space kernel (gVisor or similar) plus a policy layer that controls what agents may exec, read, write, and reach on the network (`sandbox.backend = "gvisor"` reserved).
- [ ] **Alembic** — in-place upgrades for `~/.norns` SQLite and Postgres after 0.0.1 is published.
- [ ] **Polarion field writes** — still setattr after allowlist; harden if Polarion is a real connector.
- [ ] **Worker heartbeat / lease** — stale-run recovery is age-based (`STALE_RUN_SECONDS`) and can race a live ARQ worker.
- [ ] **Multi-user / RBAC** — still one admin username/password.
