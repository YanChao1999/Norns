"""abom (Agent Bill of Materials) integration for Norns.

Homepage: https://yanchao1999.github.io/abom/

Install the CLI with::

    pip install abom
    # or with Norns: pip install 'norns-ide[abom]'

When the ``abom`` plugin is on a stage allowlist, agents can list / check /
install / link recipes (skills, prompts, MCP servers, packages). Linked skills
under a board workspace's ``.abom/`` directory are injected into the stage
system prompt automatically.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .base import Plugin, PluginContext, ToolSpec

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_SKILLS_HEADER = "## Linked agent skills (abom)"
_MCP_MARKERS = ("package.json", "pyproject.toml", "index.ts", "index.js", "server.py", "main.py")
RECIPE_KINDS = ("skill", "prompt", "mcp", "package")


@dataclass(slots=True)
class RecipeCard:
    name: str
    kind: str
    description: str
    homepage: str
    license: str
    git: str
    ref: str
    path: str | None
    installed: bool = False
    linked: bool = False


def list_recipe_cards(
    *,
    query: str | None = None,
    kind: str | None = None,
    workspace_path: str | None = None,
) -> list[RecipeCard]:
    """Structured abom catalog for the skill-store UI."""
    try:
        from abom.cli import cmd_search
        from abom.recipe import iter_recipes
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "abom is not installed. Install it with: "
            "pip install abom or pip install 'norns-ide[abom]' "
            "(docs: https://yanchao1999.github.io/abom/)"
        ) from exc

    installed = set(cmd_search(None))
    linked_names = linked_recipe_names(workspace_path)
    kind_filter = (kind or "").strip().lower() or None
    cards: list[RecipeCard] = []
    for recipe in iter_recipes(query):
        if kind_filter and recipe.kind != kind_filter:
            continue
        cards.append(
            RecipeCard(
                name=recipe.name,
                kind=recipe.kind,
                description=recipe.description,
                homepage=recipe.homepage,
                license=recipe.license,
                git=recipe.git,
                ref=recipe.ref,
                path=recipe.path,
                installed=recipe.name in installed,
                linked=recipe.name in linked_names,
            )
        )
    return cards


def linked_recipe_names(workspace_path: str | None) -> set[str]:
    """Recipe names already symlinked under ``{workspace}/.abom/``."""
    names: set[str] = set()
    for entry in _iter_abom_entries(workspace_path):
        names.add(entry.name)
    return names


def enable_recipe(name: str, *, target_repo: str | None = None) -> dict[str, Any]:
    """Install a recipe from the catalog and optionally link it into a workspace."""
    cli = _cli()
    name = name.strip()
    installed_names = set(cli.cmd_search(None))
    messages: list[str] = []
    newly_installed = False
    if name not in installed_names:
        messages.append(cli.cmd_install_recipe(name))
        newly_installed = True
    else:
        messages.append(f"already installed: {name}")

    linked = False
    target = (target_repo or "").strip()
    if target:
        links = linked_recipe_names(target)
        if name in links:
            messages.append(f"already linked: {name}")
            linked = True
        else:
            messages.append(cli.cmd_link(name, target, None))
            linked = True
    return {
        "name": name,
        "installed": True,
        "newly_installed": newly_installed,
        "linked": linked,
        "target_repo": target or None,
        "text": "\n".join(messages),
    }


def recipe_card_dict(card: RecipeCard) -> dict[str, Any]:
    return {
        "name": card.name,
        "kind": card.kind,
        "description": card.description,
        "homepage": card.homepage,
        "license": card.license,
        "git": card.git,
        "ref": card.ref,
        "path": card.path,
        "installed": card.installed,
        "linked": card.linked,
        "enabled": card.linked,
    }


def _abom_links_dir(workspace_path: str | None) -> Path | None:
    root = Path(str(workspace_path or "").strip()).expanduser()
    if not str(workspace_path or "").strip() or not root.is_dir():
        return None
    links = root / ".abom"
    return links if links.is_dir() else None


def _iter_abom_entries(workspace_path: str | None):
    links = _abom_links_dir(workspace_path)
    if links is None:
        return
    for entry in sorted(links.iterdir(), key=lambda item: item.name.lower()):
        if entry.name.startswith("."):
            continue
        yield entry


def abom_installed() -> bool:
    try:
        import abom  # noqa: F401
        from abom import cli as _cli  # noqa: F401

        return True
    except Exception:
        return False


def _cli():
    try:
        from abom import cli as abom_cli
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "abom is not installed. Install it with: "
            "pip install abom or pip install 'norns-ide[abom]' "
            "(docs: https://yanchao1999.github.io/abom/)"
        ) from exc
    return abom_cli


def _safe_cmd(name: str, *args, **kwargs) -> str:
    try:
        cli = _cli()
        result = getattr(cli, name)(*args, **kwargs)
    except Exception as exc:
        return f"error: {exc}"
    if isinstance(result, list):
        return "\n".join(str(item) for item in result) or "(none)"
    return str(result)


@dataclass(slots=True)
class LinkedSkill:
    name: str
    description: str
    body: str
    path: str


def parse_skill_markdown(text: str, *, fallback_name: str) -> LinkedSkill:
    """Parse Cursor-style SKILL.md frontmatter + body."""
    match = _FRONTMATTER_RE.match(text.strip() + ("\n" if not text.endswith("\n") else ""))
    name = fallback_name
    description = ""
    body = text.strip()
    if match:
        front, body = match.group(1), match.group(2).strip()
        for line in front.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip().lower()
            value = value.strip().strip('"').strip("'")
            if key == "name" and value:
                name = value
            elif key == "description" and value:
                description = value
    return LinkedSkill(name=name, description=description, body=body, path="")


def _resolve_material_dir(entry: Path) -> Path | None:
    """Resolve a ``.abom`` link entry to a material directory."""
    if entry.is_dir():
        return entry
    if entry.is_symlink():
        target = entry.resolve(strict=False)
        return target if target.is_dir() else None
    return None


def discover_linked_skills(workspace_path: str | None) -> list[LinkedSkill]:
    """Find skills linked into ``{workspace}/.abom/*/SKILL.md`` via ``abom link``."""
    skills: list[LinkedSkill] = []
    for entry in _iter_abom_entries(workspace_path):
        material = _resolve_material_dir(entry)
        if material is None:
            continue
        skill_md = material / "SKILL.md"
        if not skill_md.is_file():
            continue
        try:
            text = skill_md.read_text(encoding="utf-8")
        except OSError:
            continue
        skill = parse_skill_markdown(text, fallback_name=entry.name)
        skill.path = str(skill_md)
        skills.append(skill)
    return skills


@dataclass(slots=True)
class LinkedMcp:
    name: str
    command: str
    args: list[str]
    path: str


def mcp_launch_for_material(name: str, material: Path) -> LinkedMcp | None:
    """Infer a stdio MCP launch command from an abom mcp material directory."""
    if not material.is_dir():
        return None
    if not any((material / marker).is_file() for marker in _MCP_MARKERS):
        return None
    for script in ("server.py", "main.py"):
        candidate = material / script
        if candidate.is_file():
            return LinkedMcp(name=name, command=sys.executable, args=[str(candidate)], path=str(material))
    package_json = material / "package.json"
    if package_json.is_file():
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            data = {}
        if isinstance(data, dict):
            bin_field = data.get("bin")
            if isinstance(bin_field, str) and bin_field.strip():
                return LinkedMcp(
                    name=name,
                    command="node",
                    args=[str((material / bin_field).resolve())],
                    path=str(material),
                )
            if isinstance(bin_field, dict):
                for value in bin_field.values():
                    if isinstance(value, str) and value.strip():
                        return LinkedMcp(
                            name=name,
                            command="node",
                            args=[str((material / value).resolve())],
                            path=str(material),
                        )
        for script in ("index.js", "dist/index.js", "build/index.js"):
            candidate = material / script
            if candidate.is_file():
                return LinkedMcp(name=name, command="node", args=[str(candidate)], path=str(material))
        if (material / "index.ts").is_file():
            return LinkedMcp(
                name=name,
                command="npx",
                args=["-y", "--prefix", str(material), "tsx", "index.ts"],
                path=str(material),
            )
    return None


def discover_linked_mcps(workspace_path: str | None) -> list[LinkedMcp]:
    """Find MCP servers linked into ``{workspace}/.abom/`` via ``abom link``."""
    servers: list[LinkedMcp] = []
    for entry in _iter_abom_entries(workspace_path):
        material = _resolve_material_dir(entry)
        if material is None:
            continue
        # Skills win over MCP when both markers exist (skill dirs rarely have server.py).
        if (material / "SKILL.md").is_file():
            continue
        launch = mcp_launch_for_material(entry.name, material)
        if launch is not None:
            servers.append(launch)
    return servers


def skills_prompt_block(skills: list[LinkedSkill], *, max_chars: int = 24_000) -> str:
    """Build a second system message that teaches the agent about linked skills."""
    if not skills:
        return ""
    parts = [
        _SKILLS_HEADER,
        "",
        "These skills are linked into this board workspace via abom "
        "(https://yanchao1999.github.io/abom/). Follow a skill when the task matches its description.",
        "",
    ]
    used = sum(len(part) for part in parts)
    for skill in skills:
        chunk = [
            f"### Skill: {skill.name}",
            f"Path: {skill.path}" if skill.path else "",
            skill.description or "",
            "",
            skill.body,
            "",
        ]
        block = "\n".join(line for line in chunk if line is not None)
        if used + len(block) > max_chars:
            parts.append(f"### Skill: {skill.name}")
            parts.append("(truncated — skill body omitted to stay within prompt budget)")
            parts.append("")
            break
        parts.append(block)
        used += len(block)
    return "\n".join(parts).strip()


def is_skills_system_message(content: Any) -> bool:
    text = str(content or "").lstrip()
    return text.startswith(_SKILLS_HEADER)


class AbomPlugin(Plugin):
    """Manage agent skills / prompts / MCP / packages through the abom catalog."""

    name = "abom"
    title = "abom"
    description = (
        "Skill store via abom — browse, install, and enable GitHub-backed skills, prompts, "
        "MCP servers, and packages (https://yanchao1999.github.io/abom/)."
    )
    builtin = True
    requires_connector = None

    def available(self, connectors: list) -> bool:
        del connectors
        return abom_installed()

    def tools(self, context: PluginContext) -> list[ToolSpec]:
        workspace = (context.workspace_path or "").strip()

        async def list_recipes(arguments: dict[str, Any]) -> str:
            query = arguments.get("query")
            return _safe_cmd("cmd_recipes", query if isinstance(query, str) else None)

        async def show_recipe(arguments: dict[str, Any]) -> str:
            return _safe_cmd("cmd_show", str(arguments.get("name") or "").strip())

        async def check_recipe(arguments: dict[str, Any]) -> str:
            return _safe_cmd("cmd_check", str(arguments.get("name") or "").strip())

        async def install_recipe(arguments: dict[str, Any]) -> str:
            return _safe_cmd("cmd_install_recipe", str(arguments.get("name") or "").strip())

        async def search_installed(arguments: dict[str, Any]) -> str:
            query = arguments.get("query")
            return _safe_cmd("cmd_search", query if isinstance(query, str) else None)

        async def link_tool(arguments: dict[str, Any]) -> str:
            name = str(arguments.get("name") or "").strip()
            target = str(arguments.get("target_repo") or workspace).strip()
            link_name = arguments.get("link_name")
            if not target:
                return "error: target_repo is required (board workspace path is empty)"
            return _safe_cmd(
                "cmd_link",
                name,
                target,
                link_name if isinstance(link_name, str) and link_name.strip() else None,
            )

        async def remove_tool(arguments: dict[str, Any]) -> str:
            return _safe_cmd("cmd_remove", str(arguments.get("name") or "").strip())

        async def list_linked_skills(arguments: dict[str, Any]) -> str:
            del arguments
            skills = discover_linked_skills(workspace)
            if not skills:
                return (
                    f"No skills linked under {workspace or '(no workspace)'}/.abom. "
                    "Install a skill recipe, then abom_link_tool into this board folder."
                )
            lines = [f"{skill.name} — {skill.description or '(no description)'} [{skill.path}]" for skill in skills]
            return "\n".join(lines)

        return [
            ToolSpec(
                name="abom_list_recipes",
                description="List abom catalog recipes (skills, prompts, MCP servers, packages). Optional query filter.",
                input_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "additionalProperties": False,
                },
                execute=list_recipes,
            ),
            ToolSpec(
                name="abom_show_recipe",
                description="Show one abom recipe, install status, and check result.",
                input_schema={
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                    "additionalProperties": False,
                },
                execute=show_recipe,
            ),
            ToolSpec(
                name="abom_check_recipe",
                description="Verify an abom recipe's kind and install safety before installing.",
                input_schema={
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                    "additionalProperties": False,
                },
                execute=check_recipe,
            ),
            ToolSpec(
                name="abom_install_recipe",
                description="Install an abom recipe by name after the security check passes.",
                input_schema={
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                    "additionalProperties": False,
                },
                execute=install_recipe,
            ),
            ToolSpec(
                name="abom_search_installed",
                description="List installed abom tools under ABOM_HOME (default ~/.abom).",
                input_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "additionalProperties": False,
                },
                execute=search_installed,
            ),
            ToolSpec(
                name="abom_link_tool",
                description=(
                    "Symlink an installed abom tool into a repo's .abom directory. "
                    "Defaults target_repo to this stage's board workspace so skills auto-load."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "target_repo": {"type": "string"},
                        "link_name": {"type": "string"},
                    },
                    "required": ["name"],
                    "additionalProperties": False,
                },
                execute=link_tool,
            ),
            ToolSpec(
                name="abom_remove_tool",
                description="Remove an installed abom tool and its receipt.",
                input_schema={
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                    "additionalProperties": False,
                },
                execute=remove_tool,
            ),
            ToolSpec(
                name="abom_list_linked_skills",
                description="List skills already linked into this board workspace (.abom/*/SKILL.md).",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                execute=list_linked_skills,
            ),
        ]
