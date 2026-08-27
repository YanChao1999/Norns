from backend.app.plugins.tool_policy import is_write_tool


def test_write_tool_detection():
    assert is_write_tool("jira_jira_create_issue")
    assert is_write_tool("jira_jira_add_comment")
    assert is_write_tool("jira_jira_transition_issue")
    assert is_write_tool("github_work_gh_open_pr")
    assert is_write_tool("norns_update_card")
    assert is_write_tool("norns_create_card")
    assert not is_write_tool("jira_jira_search_issues")
    assert not is_write_tool("jira_jira_get_issue")
    assert not is_write_tool("norns_list_cards")
    assert not is_write_tool("norns_get_workspace")
