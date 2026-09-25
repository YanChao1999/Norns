from __future__ import annotations

from backend.app.token_usage import add_usage, attach_usage, empty_usage, usage_from_handoff, usage_from_response


def test_usage_from_response_object():
    response = type("R", (), {"usage": type("U", (), {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})()})()
    usage = usage_from_response(response)
    assert usage == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "rounds": 1, "source": "api"}


def test_add_usage_sums_rounds():
    left = usage_from_response({"usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}})
    right = usage_from_response({"usage": {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60}})
    total = add_usage(left, right)
    assert total["prompt_tokens"] == 150
    assert total["completion_tokens"] == 30
    assert total["total_tokens"] == 180
    assert total["rounds"] == 2
    assert total["source"] == "api"


def test_attach_usage_on_handoff():
    handoff = attach_usage({"summary": "ok"}, empty_usage(source="practice"), identity={"provider": "practice", "model": "none"})
    usage = usage_from_handoff(handoff)
    assert usage["source"] == "practice"
    assert usage["provider"] == "practice"
    assert usage["model"] == "none"
