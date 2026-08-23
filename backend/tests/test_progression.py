from types import SimpleNamespace

from backend.app.orchestrator.progression import is_join_stage, next_stage_after, resolve_route, resolve_routes
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


def test_resolve_routes_returns_all_default_targets():
    stages = [
        SimpleNamespace(id="interface", order=1),
        SimpleNamespace(id="tests", order=2, lane=0),
        SimpleNamespace(id="software", order=2, lane=1),
        SimpleNamespace(id="integration", order=3),
    ]
    edges = [
        _edge(from_stage_id="interface", to_stage_id="tests", order=0),
        _edge(from_stage_id="interface", to_stage_id="software", order=1),
    ]
    routes = resolve_routes(stages, edges, "interface", "approve", {})
    assert [route.stage_id for route in routes] == ["tests", "software"]
    assert all(route.found for route in routes)


def test_matching_if_skips_parallel_defaults():
    stages = [
        SimpleNamespace(id="a", order=1),
        SimpleNamespace(id="b", order=2),
        SimpleNamespace(id="c", order=2),
    ]
    edges = [
        _edge(to_stage_id="b", condition_key="risk", condition_value="high", order=0),
        _edge(to_stage_id="b", order=1),
        _edge(to_stage_id="c", order=2),
    ]
    exclusive = resolve_routes(stages, edges, "a", "approve", {"risk": "high"})
    assert [route.stage_id for route in exclusive] == ["b"]
    split = resolve_routes(stages, edges, "a", "approve", {"risk": "low"})
    assert [route.stage_id for route in split] == ["b", "c"]


def test_resolve_routes_ignores_back_edges_when_splitting():
    stages = [
        SimpleNamespace(id="urd", order=1, lane=0),
        SimpleNamespace(id="arch", order=2, lane=0),
        SimpleNamespace(id="software", order=3, lane=0),
        SimpleNamespace(id="test", order=3, lane=1),
    ]
    edges = [
        _edge(from_stage_id="arch", to_stage_id="urd", order=0),
        _edge(from_stage_id="arch", to_stage_id="software", order=1),
        _edge(from_stage_id="arch", to_stage_id="test", order=2),
    ]
    routes = resolve_routes(stages, edges, "arch", "approve", {})
    assert [route.stage_id for route in routes] == ["software", "test"]


def test_join_stage_ignores_back_edges_to_earlier_columns():
    stages = [
        SimpleNamespace(id="urd", order=1, lane=0),
        SimpleNamespace(id="software", order=3, lane=0),
        SimpleNamespace(id="test", order=3, lane=1),
        SimpleNamespace(id="qa", order=4, lane=0),
    ]
    edges = [
        _edge(from_stage_id="software", to_stage_id="urd"),
        _edge(from_stage_id="test", to_stage_id="urd"),
        _edge(from_stage_id="software", to_stage_id="qa"),
        _edge(from_stage_id="test", to_stage_id="qa"),
    ]
    assert is_join_stage(edges, "urd", stages) is False
    assert is_join_stage(edges, "qa", stages) is True


def test_join_stage_has_two_incoming_default_lines():
    stages = [
        SimpleNamespace(id="tests", order=2, lane=0),
        SimpleNamespace(id="software", order=2, lane=1),
        SimpleNamespace(id="integration", order=3, lane=0),
    ]
    edges = [
        _edge(from_stage_id="tests", to_stage_id="integration"),
        _edge(from_stage_id="software", to_stage_id="integration"),
    ]
    assert is_join_stage(edges, "integration", stages) is True
    assert is_join_stage(edges, "tests", stages) is False


def test_empty_contains_does_not_match():
    stages = [SimpleNamespace(id="a", order=1), SimpleNamespace(id="b", order=2), SimpleNamespace(id="c", order=3)]
    edges = [
        _edge(to_stage_id="b", condition_key="summary", condition_op="contains", condition_value="", order=0),
        _edge(to_stage_id="c", order=1),
    ]
    route = resolve_route(stages, edges, "a", "approve", {"summary": "anything"})
    assert route.stage_id == "c"


def test_return_card_to_previous_stage():
    card = SimpleNamespace(status=CardStatus.WAITING_APPROVAL, current_stage_id="stage-b")
    return_card_to_stage(card, "stage-a")
    assert card.current_stage_id == "stage-a"
    assert card.status == CardStatus.IDLE
