from backend.app.tools.registry import RuntimeTool, ToolRegistry


def _tool(name: str) -> RuntimeTool:
    async def execute(arguments: dict) -> dict:
        return arguments

    return RuntimeTool(name=name, openai_tool={"type": "function", "function": {"name": name}}, execute=execute)


def test_empty_allowlist_returns_no_tools():
    registry = ToolRegistry()
    registry.register_provider("github", lambda _connectors: [_tool("github_read")])
    registry.register_provider("jira", lambda _connectors: [_tool("jira_get")])
    assert registry.get_runtime_tools([], []) == []


def test_allowlist_selects_named_providers_only():
    registry = ToolRegistry()
    registry.register_provider("github", lambda _connectors: [_tool("github_read")])
    registry.register_provider("jira", lambda _connectors: [_tool("jira_get")])
    tools = registry.get_runtime_tools(["jira"], [])
    assert [tool.name for tool in tools] == ["jira_get"]
