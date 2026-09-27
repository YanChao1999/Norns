from __future__ import annotations

from pathlib import Path

from backend.app.plugins.abom_plugin import (
    AbomPlugin,
    discover_linked_mcps,
    discover_linked_skills,
    enable_recipe,
    list_recipe_cards,
    mcp_launch_for_material,
    parse_skill_markdown,
    skills_prompt_block,
)
from backend.app.plugins.base import PluginContext
from backend.app.plugins.catalog import cursor_mcp_servers, load_plugin_catalog
from backend.app.token_usage import summarize_round_input


def test_catalog_includes_abom_plugin():
    catalog = load_plugin_catalog([])
    assert "abom" in catalog.by_name()
    names = {spec.name for spec in catalog.tools(["abom"], PluginContext(workspace_path="/tmp"))}
    assert "abom_list_recipes" in names
    assert "abom_install_recipe" in names
    assert "abom_link_tool" in names
    assert "abom_list_linked_skills" in names


def test_parse_and_discover_linked_skills(tmp_path: Path):
    skill_dir = tmp_path / ".abom" / "demo-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: Helps with demos.\n---\n\n# Demo\n\nDo the demo carefully.\n",
        encoding="utf-8",
    )
    skills = discover_linked_skills(str(tmp_path))
    assert len(skills) == 1
    assert skills[0].name == "demo-skill"
    assert "demo" in skills[0].description.lower()
    block = skills_prompt_block(skills)
    assert "## Linked agent skills (abom)" in block
    assert "Do the demo carefully." in block

    parsed = parse_skill_markdown("# bare\n", fallback_name="bare")
    assert parsed.name == "bare"


def test_discover_linked_mcps_and_cursor_attach(tmp_path: Path):
    mcp_dir = tmp_path / ".abom" / "demo-mcp"
    mcp_dir.mkdir(parents=True)
    (mcp_dir / "server.py").write_text("print('mcp')\n", encoding="utf-8")
    linked = discover_linked_mcps(str(tmp_path))
    assert len(linked) == 1
    assert linked[0].name == "demo-mcp"
    assert linked[0].args[-1].endswith("server.py")
    launch = mcp_launch_for_material("demo-mcp", mcp_dir)
    assert launch is not None
    servers = cursor_mcp_servers(["abom"], [], workspace_path=str(tmp_path))
    assert "abom_demo_mcp" in servers
    assert servers["abom_demo_mcp"]["command"] == launch.command
    assert servers["abom_demo_mcp"]["args"] == launch.args
    # Without abom on the allowlist, linked MCPs stay detached.
    assert "abom_demo_mcp" not in cursor_mcp_servers(["norns"], [], workspace_path=str(tmp_path))


def test_list_recipe_cards_skill_store(tmp_path: Path, monkeypatch):
    from types import SimpleNamespace

    fake_recipes = [
        SimpleNamespace(
            name="abom-skill",
            kind="skill",
            description="Skill helper",
            homepage="https://yanchao1999.github.io/abom/",
            license="MIT",
            git="https://github.com/YanChao1999/abom.git",
            ref="main",
            path="skills/abom",
        ),
        SimpleNamespace(
            name="abom-mcp",
            kind="mcp",
            description="MCP helper",
            homepage="https://yanchao1999.github.io/abom/",
            license="MIT",
            git="https://github.com/YanChao1999/abom.git",
            ref="main",
            path="mcp",
        ),
    ]

    fake_abom_cli = SimpleNamespace(cmd_search=lambda _q: ["abom-skill"])
    fake_abom_recipe = SimpleNamespace(iter_recipes=lambda _q: fake_recipes)
    import sys

    monkeypatch.setitem(sys.modules, "abom", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "abom.cli", fake_abom_cli)
    monkeypatch.setitem(sys.modules, "abom.recipe", fake_abom_recipe)

    cards = list_recipe_cards(kind="skill")
    assert len(cards) == 1
    assert cards[0].name == "abom-skill"
    assert cards[0].installed is True
    assert cards[0].linked is False

    link = tmp_path / ".abom" / "abom-skill"
    link.mkdir(parents=True)
    (link / "SKILL.md").write_text("---\nname: abom\ndescription: x\n---\n\nbody\n", encoding="utf-8")
    linked = list_recipe_cards(kind="skill", workspace_path=str(tmp_path))
    assert linked[0].linked is True


def test_enable_recipe_installs_and_links(tmp_path: Path, monkeypatch):
    calls: list[tuple] = []

    class FakeCli:
        @staticmethod
        def cmd_search(_query):
            return []

        @staticmethod
        def cmd_install_recipe(name):
            calls.append(("install", name))
            return f"installed {name}"

        @staticmethod
        def cmd_link(name, target, link_name):
            calls.append(("link", name, target, link_name))
            dest = Path(target) / ".abom" / name
            dest.mkdir(parents=True, exist_ok=True)
            return f"linked {name} -> {dest}"

    monkeypatch.setattr("backend.app.plugins.abom_plugin._cli", lambda: FakeCli())
    # enable_recipe imports cmd_search via _cli after our patch — also patch list path used before install
    result = enable_recipe("demo-skill", target_repo=str(tmp_path))
    assert result["installed"] is True
    assert result["linked"] is True
    assert result["newly_installed"] is True
    assert ("install", "demo-skill") in calls
    assert any(item[0] == "link" for item in calls)


def test_input_breakdown_counts_skills_system_message():
    breakdown = summarize_round_input(
        [
            {"role": "system", "content": "You are Urd."},
            {
                "role": "system",
                "content": "## Linked agent skills (abom)\n\n### Skill: demo\nbody " + ("x" * 80),
            },
            {"role": "user", "content": "task"},
        ],
        None,
    )
    assert breakdown["system"] > 0
    assert breakdown["skills"] > 0
    assert breakdown["task"] > 0


def test_abom_plugin_tools_without_package_return_install_hint(monkeypatch):
    plugin = AbomPlugin()

    def boom():
        raise RuntimeError("missing")

    monkeypatch.setattr("backend.app.plugins.abom_plugin._cli", boom)
    # Force available path through tools execute when abom import fails inside _cli
    import asyncio

    async def run():
        tools = {spec.name: spec for spec in plugin.tools(PluginContext())}
        result = await tools["abom_list_recipes"].execute({})
        assert "abom is not installed" in result or "error:" in result

    asyncio.run(run())
