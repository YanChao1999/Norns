"""Token usage helpers for stage agent runs.

Stored on each AgentRun as ``handoff["usage"]`` so one card (task) can show a
matrix of cost/effect across stages (agents) without a schema migration.

OpenAI/DeepSeek: ``response.usage`` from chat completions.
Cursor: ``TokenUsage`` / ``AgentUsage`` from cursor-sdk (``run.wait()`` or
``agent.get_usage()``).
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
    return _normalize_token_counts(usage, source="api", rounds=1)


def usage_from_cursor(raw: Any, *, rounds: int = 1) -> dict[str, Any]:
    """Map Cursor SDK TokenUsage / AgentUsage / dict into Norns usage shape.

    Cursor uses input/output (+ optional cache) tokens; we map input→prompt and
    output→completion so the card matrix stays one schema.
    """
    if raw is None:
        return empty_usage(source="unavailable", rounds=rounds)
    nested = getattr(raw, "usage", None)
    unwrap = (
        nested is not None
        and not isinstance(raw, dict)
        and (
            hasattr(nested, "input_tokens")
            or hasattr(nested, "output_tokens")
            or (isinstance(nested, dict) and _has_token_fields(nested))
        )
    )
    if unwrap:
        # AgentUsage.usage or RunResult.usage → TokenUsage
        raw = nested
    if isinstance(raw, dict) and "usage" in raw and not _has_token_fields(raw):
        raw = raw.get("usage")
    if raw is None:
        return empty_usage(source="unavailable", rounds=rounds)
    return _normalize_token_counts(raw, source="cursor", rounds=rounds)


def _has_token_fields(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    keys = {
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "input_tokens",
        "output_tokens",
        "inputTokens",
        "outputTokens",
        "totalTokens",
        "cache_read_tokens",
        "cacheReadTokens",
        "cache_write_tokens",
        "cacheWriteTokens",
    }
    return any(key in value and value.get(key) is not None for key in keys)


def _object_has_token_attrs(value: Any) -> bool:
    return any(
        getattr(value, name, None) is not None
        for name in (
            "prompt_tokens",
            "completion_tokens",
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
        )
    )


def _normalize_token_counts(usage: Any, *, source: str, rounds: int) -> dict[str, Any]:
    if isinstance(usage, dict):
        prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or usage.get("inputTokens") or 0)
        completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or usage.get("outputTokens") or 0)
        cache_read = int(usage.get("cache_read_tokens") or usage.get("cacheReadTokens") or 0)
        cache_write = int(usage.get("cache_write_tokens") or usage.get("cacheWriteTokens") or 0)
        total = int(usage.get("total_tokens") or usage.get("totalTokens") or 0)
    else:
        prompt = int(getattr(usage, "prompt_tokens", None) or getattr(usage, "input_tokens", None) or 0)
        completion = int(getattr(usage, "completion_tokens", None) or getattr(usage, "output_tokens", None) or 0)
        cache_read = int(getattr(usage, "cache_read_tokens", None) or 0)
        cache_write = int(getattr(usage, "cache_write_tokens", None) or 0)
        total = int(getattr(usage, "total_tokens", None) or 0)
    if not total:
        total = prompt + completion + cache_read + cache_write
    if (
        prompt == 0
        and completion == 0
        and total == 0
        and not _has_token_fields(usage)
        and not _object_has_token_attrs(usage)
    ):
        return empty_usage(source="unavailable", rounds=rounds)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
        "rounds": int(rounds),
        "source": source,
    }


def add_usage(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any]:
    a = left if isinstance(left, dict) else empty_usage()
    b = right if isinstance(right, dict) else empty_usage()
    sources = {str(a.get("source") or ""), str(b.get("source") or "")} - {"", "unavailable"}
    if "api" in sources:
        source = "api"
    elif "cursor" in sources:
        source = "cursor"
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


def attach_usage(
    handoff: dict[str, Any], usage: dict[str, Any] | None, *, identity: dict[str, Any] | None = None
) -> dict[str, Any]:
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
