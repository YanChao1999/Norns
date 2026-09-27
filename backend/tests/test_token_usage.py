from __future__ import annotations

from backend.app.token_usage import (
    add_usage,
    attach_usage,
    empty_usage,
    estimate_tokens,
    summarize_round_input,
    usage_from_cursor,
    usage_from_handoff,
    usage_from_response,
)


def test_usage_from_response_object():
    response = type(
        "R", (), {"usage": type("U", (), {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})()}
    )()
    usage = usage_from_response(response)
    assert usage == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "rounds": 1, "source": "api"}


def test_usage_from_cursor_token_usage():
    usage = usage_from_cursor(
        type(
            "T",
            (),
            {
                "input_tokens": 80,
                "output_tokens": 20,
                "cache_read_tokens": 10,
                "cache_write_tokens": 0,
                "total_tokens": 110,
            },
        )()
    )
    assert usage["source"] == "cursor"
    assert usage["prompt_tokens"] == 80
    assert usage["completion_tokens"] == 20
    assert usage["total_tokens"] == 110


def test_usage_from_cursor_agent_usage_wrapper():
    token = type(
        "T",
        (),
        {
            "input_tokens": 5,
            "output_tokens": 2,
            "total_tokens": 7,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
        },
    )()
    agent_usage = type("A", (), {"usage": token, "runs": (), "cost": None})()
    usage = usage_from_cursor(agent_usage)
    assert usage["prompt_tokens"] == 5
    assert usage["completion_tokens"] == 2
    assert usage["source"] == "cursor"


def test_add_usage_sums_rounds():
    left = usage_from_response({"usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}})
    right = usage_from_response({"usage": {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60}})
    total = add_usage(left, right)
    assert total["prompt_tokens"] == 150
    assert total["completion_tokens"] == 30
    assert total["total_tokens"] == 180
    assert total["rounds"] == 2
    assert total["source"] == "api"


def test_add_usage_prefers_cursor_source():
    total = add_usage(
        empty_usage(source="unavailable"),
        {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "rounds": 1, "source": "cursor"},
    )
    assert total["source"] == "cursor"


def test_attach_usage_on_handoff():
    handoff = attach_usage(
        {"summary": "ok"}, empty_usage(source="practice"), identity={"provider": "practice", "model": "none"}
    )
    usage = usage_from_handoff(handoff)
    assert usage["source"] == "practice"
    assert usage["provider"] == "practice"
    assert usage["model"] == "none"


def test_summarize_round_input_splits_roles_and_tool_schemas():
    tools = [{"type": "function", "function": {"name": "jira_search", "parameters": {"type": "object"}}}]
    breakdown = summarize_round_input(
        [
            {"role": "system", "content": "You are Urd. " * 20},
            {"role": "user", "content": "Card body and prior handoff. " * 20},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "1", "function": {"name": "jira_search"}}]},
            {"role": "tool", "content": '{"issues": []}' * 30},
        ],
        tools,
    )
    assert breakdown["system"] > 0
    assert breakdown["task"] > 0
    assert breakdown["tool_schemas"] > 0
    assert breakdown["assistant"] > 0
    assert breakdown["tool_results"] > 0
    assert breakdown["skills"] == 0
    assert breakdown["estimated_prompt"] == (
        breakdown["system"]
        + breakdown["task"]
        + breakdown["tool_schemas"]
        + breakdown["assistant"]
        + breakdown["tool_results"]
        + breakdown["skills"]
    )
    assert breakdown["kind"] == "estimate"
    assert estimate_tokens("abcd") == 1


def test_add_usage_merges_input_breakdown():
    left = {
        "prompt_tokens": 10,
        "completion_tokens": 1,
        "total_tokens": 11,
        "rounds": 1,
        "source": "api",
        "input_breakdown": {
            "method": "chars/4",
            "kind": "estimate",
            "system": 5,
            "task": 4,
            "tool_schemas": 3,
            "assistant": 0,
            "tool_results": 0,
            "skills": 0,
            "estimated_prompt": 12,
        },
    }
    right = {
        "prompt_tokens": 20,
        "completion_tokens": 2,
        "total_tokens": 22,
        "rounds": 1,
        "source": "api",
        "input_breakdown": {
            "method": "chars/4",
            "kind": "estimate",
            "system": 5,
            "task": 4,
            "tool_schemas": 3,
            "assistant": 2,
            "tool_results": 8,
            "skills": 0,
            "estimated_prompt": 22,
        },
    }
    total = add_usage(left, right)
    assert total["input_breakdown"]["tool_schemas"] == 6
    assert total["input_breakdown"]["tool_results"] == 8
    assert total["input_breakdown"]["estimated_prompt"] == 34
