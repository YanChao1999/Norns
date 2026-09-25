"""Token usage helpers for OpenAI-compatible chat completions.

Stored on each AgentRun as ``handoff["usage"]`` so one card (task) can show a
matrix of cost/effect across stages (agents) without a schema migration.
"""

from __future__ import annotations

from typing import Any


def empty_usage(*, source: str = "unavailable", rounds: int = 0) -> dict[str, Any]:
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "rounds": int(rounds),
        "source": source,
    }


def usage_from_response(response: Any) -> dict[str, Any]:
    """Pull prompt/completion/total tokens from an OpenAI SDK response, if present."""
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")
    if usage is None:
        return empty_usage(source="unavailable", rounds=1)
    if isinstance(usage, dict):
        prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        total = int(usage.get("total_tokens") or (prompt + completion))
    else:
        prompt = int(getattr(usage, "prompt_tokens", None) or getattr(usage, "input_tokens", None) or 0)
        completion = int(getattr(usage, "completion_tokens", None) or getattr(usage, "output_tokens", None) or 0)
        total = int(getattr(usage, "total_tokens", None) or (prompt + completion))
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total if total else prompt + completion,
        "rounds": 1,
        "source": "api",
    }


def add_usage(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any]:
    a = left if isinstance(left, dict) else empty_usage()
    b = right if isinstance(right, dict) else empty_usage()
    sources = {str(a.get("source") or ""), str(b.get("source") or "")} - {"", "unavailable"}
    if "api" in sources:
        source = "api"
    elif "practice" in sources:
        source = "practice"
    elif sources:
        source = sorted(sources)[0]
    else:
        source = "unavailable"
    prompt = int(a.get("prompt_tokens") or 0) + int(b.get("prompt_tokens") or 0)
    completion = int(a.get("completion_tokens") or 0) + int(b.get("completion_tokens") or 0)
    total = int(a.get("total_tokens") or 0) + int(b.get("total_tokens") or 0)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total if total else prompt + completion,
        "rounds": int(a.get("rounds") or 0) + int(b.get("rounds") or 0),
        "source": source,
    }


def attach_usage(handoff: dict[str, Any], usage: dict[str, Any] | None, *, identity: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(handoff or {})
    entry = dict(usage or empty_usage())
    if identity:
        entry["provider"] = str(identity.get("provider") or "")
        entry["model"] = str(identity.get("model") or "")
    payload["usage"] = entry
    return payload


def usage_from_handoff(handoff: Any) -> dict[str, Any]:
    if not isinstance(handoff, dict):
        return empty_usage()
    raw = handoff.get("usage")
    if not isinstance(raw, dict):
        return empty_usage()
    return {
        "prompt_tokens": int(raw.get("prompt_tokens") or 0),
        "completion_tokens": int(raw.get("completion_tokens") or 0),
        "total_tokens": int(raw.get("total_tokens") or 0),
        "rounds": int(raw.get("rounds") or 0),
        "source": str(raw.get("source") or "unavailable"),
        "provider": str(raw.get("provider") or (handoff.get("llm") or {}).get("provider") or ""),
        "model": str(raw.get("model") or (handoff.get("llm") or {}).get("model") or ""),
    }
