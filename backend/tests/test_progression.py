from types import SimpleNamespace

from backend.app.orchestrator.progression import next_stage_after, resolve_route
from backend.app.orchestrator.state_machine import CardStatus, auto_advance_card, return_card_to_stage


def test_next_stage_after_returns_following_stage():
    stage_a = SimpleNamespace(id="a", order=1)
    stage_b = SimpleNamespace(id="b", order=2)
    stage_c = SimpleNamespace(id="c", order=3)
    assert next_stage_after([stage_c, stage_a, stage_b], "a").id == "b"
    assert next_stage_after([stage_a, stage_b, stage_c], "c") is None
    assert next_stage_after([stage_a], "missing") is None


def test_auto_advance_moves_to_next_stage_while_running():
    card = SimpleNamespace(status=CardStatus.RUNNING, current_stage_id="stage-a")
    auto_advance_card(card, "stage-b")
    assert card.current_stage_id == "stage-b"
    assert card.status == CardStatus.RUNNING


def test_auto_advance_last_stage_marks_done():
    card = SimpleNamespace(status=CardStatus.RUNNING, current_stage_id="stage-a")
    auto_advance_card(card, None)
    assert card.status == CardStatus.DONE


def _edge(**kwargs):
    defaults = {
        "from_stage_id": "a",
        "to_stage_id": "b",
        "event": "approve",
        "condition_key": "",
        "condition_op": "eq",
        "condition_value": "",
        "order": 0,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_resolve_route_prefers_matching_if_then_default():
    stages = [SimpleNamespace(id="a", order=1), SimpleNamespace(id="b", order=2), SimpleNamespace(id="c", order=3)]
    edges = [
        _edge(to_stage_id="a", condition_key="risk", condition_value="high", order=0),
        _edge(to_stage_id="c", order=1),
    ]
    back = resolve_route(stages, edges, "a", "approve", {"risk": "high"})
    assert back.found is True
    assert back.stage_id == "a"
    forward = resolve_route(stages, edges, "a", "approve", {"risk": "low"})
    assert forward.stage_id == "c"


def test_resolve_route_can_branch_on_agent_recommendation():
    stages = [SimpleNamespace(id="a", order=1), SimpleNamespace(id="b", order=2)]
    edges = [
        _edge(to_stage_id="a", event="approve", condition_key="recommendation", condition_value="reject", order=0),
        _edge(to_stage_id="b", event="approve", order=1),
    ]
    back = resolve_route(stages, edges, "a", "approve", {"recommendation": "reject"})
    assert back.stage_id == "a"
    forward = resolve_route(stages, edges, "a", "approve", {"recommendation": "approve"})
    assert forward.stage_id == "b"


def test_resolve_route_reject_without_line_is_not_found():
    stages = [SimpleNamespace(id="a", order=1), SimpleNamespace(id="b", order=2)]
    route = resolve_route(stages, [], "b", "reject", {})
    assert route.found is False


def test_return_card_to_previous_stage():
    card = SimpleNamespace(status=CardStatus.WAITING_APPROVAL, current_stage_id="stage-b")
    return_card_to_stage(card, "stage-a")
    assert card.current_stage_id == "stage-a"
    assert card.status == CardStatus.IDLE
