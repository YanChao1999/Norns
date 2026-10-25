# Roadmap

Shipped on `main` through **0.0.4** (on PyPI): early 0.0.3 plus Command Light Control Room (#48), A-class first-run / practice / git-bind (#47), system-proxy Settings (#52), token usage matrix (#54), abom skill store (#59), refreshed Pages (#61), downloads chart (#65), and first-run tool warnings (#66).

**Positioning:** Norns is **agent-first** — each column is an agent whose primary job is orchestrating **tools + skills** (allowlist, abom, MCP). Handoff stays thin (summary / decision / artifacts). Contrast with workflow tools like n8n that orchestrate steps and integrations first.

This file is the remaining backlog. Open GitHub issues without an `A` label still track follow-ups; A-class alpha feedback from #18–#39 is closed on `main`.

## Now

### Agent-first (tools / skills)

- [x] **Agent workbench** — column + Agent dialog lead with tools and linked skills (what can run, missing connector, abom links); weaken “flow node” framing. Closes [#28](https://github.com/YanChao1999/Norns/issues/28).
- [x] **Tool / skill bakeoff** — same prompt on parallel arms with different allowlists; compare tokens + outcome (lands [#55](https://github.com/YanChao1999/Norns/pull/55)).
- [x] **Skills as first-class** — per-stage / Agent dialog skill list (name, abom source, injected when abom allowlisted); handoff stays summary/decision only.

### Already shipped (checklist)

- [x] **pip / uv install** — `uv tool install norns-ide` / `pip install norns-ide` (or `uv tool install .` from a checkout). CI checks the wheel, sdist, packaged UI, and `/api/health`.
- [x] **Publish 0.0.2 as `norns-ide`** — on PyPI / TestPyPI. Follow [PUBLISH.md](PUBLISH.md) for the next cut.
- [x] **Parallel planned split + sandbox** — soft join (no wait/merge); previous column plans `handoff.tracks`; directory or hardened Docker sandbox per agent run.
- [x] **Command Light Control Room** — Command Light theme + Night stub, practice chrome, soft join UI, Settings write gate, card detail sheet (#48).
- [x] **System proxy preference** — Settings → Network toggle (or `USE_SYSTEM_PROXY` / `[network] use_system_proxy`); Clash `socks://` normalized to `socks5://`; off = direct API egress (#52).
- [x] **Token usage matrix** — capture OpenAI/DeepSeek/Cursor usage per stage run; card detail + board summary; input breakdown reference for MCP/tools/skills (#54).
- [x] **abom skill store** — Agent Config skill store; **Enable** installs + links GitHub recipes into `.abom/`; skills inject into prompts; MCP recipes auto-attach for Cursor ([abom](https://yanchao1999.github.io/abom/), #59).
- [x] **Publish 0.0.3** — early cut on PyPI (2026-09-26); superseded by 0.0.4 for abom + token usage.
- [x] **Publish 0.0.4** — on PyPI (`norns-ide==0.0.4`, optional `[abom]`); tag [v0.0.4](https://github.com/YanChao1999/Norns/releases/tag/v0.0.4).

### Deferred infra

- Sandbox microVM / gVisor backends
- Alembic migrations, multi-user / RBAC, worker lease hardening

## First-use / Control Room (alpha A-class)

- [x] **Connector form in Settings** — OpenAI, Cursor, DeepSeek, Jira, GitHub, Polarion (plus MCP / workspace).
- [x] **API key in Settings** — encrypted connectors; env/`config.toml` still works as a fallback.
- [x] **Agent setup path** — column **Agent** opens prompt / model / tools; empty allowlist grants no tools.
- [x] **Empty state after login** — checklist CTA into Settings; create board → model → optional Bind git → run.
- [x] **Sample card on new boards** — seeded “first practice run” card so the board is not empty.
- [x] **Practice vs real** — practice banner + Settings CTA when `llm_configured` is false; practice chips / gate labels; practice does not auto-pass to `done`.
- [x] **Fake-key health** — model-list auth failure keeps `usable` / `llm_configured` false.
- [x] **Failed runs → blocked** — stage failures align with human reject (`blocked`), not `idle`.
- [x] **Bind git validation** — path must exist; `git_url` must look like a git remote; `/api/workspace?board_id=` reflects the board.
- [x] **Warn when tools have no connector** — Agent dialog notices for empty allowlist and checked plugins without a connector/CLI; board column shows `no tools — open Agent`.
- [x] **Login copy** — username is `admin`; password was printed by `norns init` and is in `~/.norns/config.toml`.

## Docs / install leftovers

- [x] **Pages install snippet** — `docs/index.html` install path is PyPI / TestPyPI `norns-ide` for 0.0.4.
- [x] **README downloads** — monthly badge + daily trend chart (`assets/downloads-trend.svg`).

## After first use / publish

- [x] **Hardened Docker sandbox** — bind-mounted copy only, `--cap-drop ALL`, read-only rootfs, no-new-privileges (`sandbox.backend = "docker"`).
- [x] **Sandbox MCP plugin** — allowlist `sandbox` for info / run / list-read-write / copy-in.
- [x] **Cursor live model catalog** — `GET /v1/models` (with SDK fallback); remap OpenAI-only ids for Cursor Cloud Agents.
- [x] **Wait countdown** — UI counts down toward Cursor timeout instead of only elapsed time.
- [ ] **Sandbox microVM backend** — stronger isolation when containers are not enough (`sandbox.backend = "microvm"`). Prefer hardened `docker` until then.
- [ ] **gVisor + agent runtime policy** — user-space kernel plus policy for exec / IO / network (`sandbox.backend = "gvisor"` reserved).
- [ ] **Alembic** — in-place upgrades for `~/.norns` SQLite and Postgres after a stable published line.
- [ ] **Polarion field writes** — still setattr after allowlist; harden if Polarion is a real connector.
- [ ] **Worker heartbeat / lease** — stale-run recovery is age-based (`STALE_RUN_SECONDS`) and can race a live ARQ worker.
- [ ] **Multi-user / RBAC** — still one admin username/password.
