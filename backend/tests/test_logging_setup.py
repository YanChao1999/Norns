from __future__ import annotations

import logging

from backend.app.logging_setup import QuietAccessFilter, compact_error_for_log, uvicorn_log_config


def test_compact_error_strips_cursor_model_catalog():
    detail = (
        "HTTP 400: invalid_argument: Cannot use this model: gpt-4o. "
        "Available models: default, grok-4.6, composer-2.5, claude-opus-5"
    )
    short = compact_error_for_log(detail)
    assert "gpt-4o" in short
    assert "Available models" not in short
    assert "see run output" in short


def test_quiet_access_filter_drops_health_and_polls():
    filt = QuietAccessFilter()
    health = logging.LogRecord(
        "uvicorn.access", logging.INFO, "", 0, '%s - "%s" %s', ("127.0.0.1:1", "GET /api/health HTTP/1.1", "200"), None
    )
    # uvicorn AccessFormatter builds getMessage from args; set msg already formatted for the filter
    health.msg = '127.0.0.1:1 - "GET /api/health HTTP/1.1" 200'
    health.args = ()
    assert filt.filter(health) is False

    poll = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, "%s", (), None)
    poll.msg = '127.0.0.1:1 - "GET /api/cards/abc/runs HTTP/1.1" 200 OK'
    assert filt.filter(poll) is False

    board_poll = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, "%s", (), None)
    board_poll.msg = '127.0.0.1:1 - "GET /api/boards/b1 HTTP/1.1" 200'
    assert filt.filter(board_poll) is False

    run = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, "%s", (), None)
    run.msg = '127.0.0.1:1 - "POST /api/cards/abc/run HTTP/1.1" 202 Accepted'
    assert filt.filter(run) is True

    health_fail = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, "%s", (), None)
    health_fail.msg = '127.0.0.1:1 - "GET /api/health HTTP/1.1" 500'
    assert filt.filter(health_fail) is True


def test_uvicorn_log_config_wires_norns_logger():
    config = uvicorn_log_config()
    assert "norns" in config["loggers"]
    assert config["loggers"]["norns"]["propagate"] is False
    assert "quiet_access" in config["filters"]
    assert config["handlers"]["access"]["filters"] == ["quiet_access"]
