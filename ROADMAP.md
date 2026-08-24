# Roadmap

Shipped on `main`: 0.0.1 Control Room loop (boards, Machine editor, human gates, parallel split/join, local `norns init` / `norns run`).

This file is the first-use backlog. **Now:** pip / uv install (`feat/pip-uv-install`). Everything else stays here until it has its own branch.

## Now

- [ ] **pip / uv install** — `uv tool install .` / `pip install .` (and later `pip install norns`) so first run is not uv + two npm trees. In progress on `feat/pip-uv-install`.
- [ ] **Publish 0.0.1 to PyPI** — so `uv tool install norns` and `pip install norns` work without a git checkout. Needs a PyPI token / trusted publisher.

## First-use Settings (users cannot finish setup in the UI)

- [ ] **Connector form in Settings** — add/edit/disable Jira, GitHub, Polarion. Jira needs `server`, `username`, `token`. GitHub needs `token` (optional `base_url`). Polarion needs `server`, `username`, `password`, optional `project`. Today Settings only lists “No connectors configured.” The API already exists (`POST /api/connectors`).
- [ ] **API key in Settings** — OpenAI-compatible API key, base URL, and default model. Today this is `~/.norns/config.toml` only.
- [ ] **Agent setup path** — explain that the column **Agent** button opens prompt / model / tools; an empty tool allowlist grants no tools; checking `jira` / `github` / `polarion` requires an active connector of that type.
- [ ] **Warn when tools have no connector** — do not silently grant nothing.
- [ ] **Empty state after login** — with no boards, land in Settings (or a short checklist): create board → API key → connector if you need tools → open the board.
- [ ] **Login copy** — username is `admin`; password was printed by `norns init` and is in `~/.norns/config.toml`.

## Docs / install leftovers

- [ ] **Pages install snippet** — `docs/index.html` still says `git checkout cursor/v0.0.1-first-production`. Point it at `main`.
- [ ] **Sample board / card** — optional seeded work so the first session is not an empty board.

## After first use / publish

- [ ] **Alembic** — in-place upgrades for `~/.norns` SQLite and Postgres after 0.0.1 is published.
- [ ] **Polarion field writes** — still setattr after allowlist; harden if Polarion is a real connector.
- [ ] **Worker heartbeat / lease** — stale-run recovery is age-based (`STALE_RUN_SECONDS`) and can race a live ARQ worker.
- [ ] **Multi-user / RBAC** — still one admin username/password.
