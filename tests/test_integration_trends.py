from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "custom_components" / "home_assistant_health_manager" / "integration_trends.py"
SPEC = spec_from_file_location("health_manager_integration_trends", MODULE_PATH)
TRENDS = module_from_spec(SPEC)
SPEC.loader.exec_module(TRENDS)


def inventory(domain="mqtt", unavailable=0, unknown=0, errors=0, retries=0):
    signals = []
    if errors:
        signals.append("setup_error")
    if retries:
        signals.append("setup_retry")
    if unavailable:
        signals.append("unavailable_entities")
    if unknown:
        signals.append("unknown_entities")
    return {
        "integration_domain_count": 1,
        "inventory_truncated": False,
        "integrations": [{
            "domain": domain,
            "config_entry_count": 1,
            "setup_states": {"setup_error": errors, "setup_retry": retries, "loaded": 1},
            "entity_count": 10,
            "unavailable_entity_count": unavailable,
            "unknown_entity_count": unknown,
        }],
    }


def test_first_integration_sample_has_no_false_recurrence():
    history, summary = TRENDS.update_integration_trend_history(
        [], inventory(unavailable=2), "2026-11-14T00:00:00Z"
    )
    assert len(history) == 1
    assert summary["active_attention_domain_count"] == 1
    assert summary["domains"][0]["attention_episodes"] == 1
    assert summary["domains"][0]["recurring_attention"] is False


def test_continuous_attention_counts_as_one_episode():
    history, _ = TRENDS.update_integration_trend_history(
        [], inventory(unavailable=2), "2026-11-14T00:00:00Z"
    )
    history, summary = TRENDS.update_integration_trend_history(
        history, inventory(unavailable=3), "2026-11-21T00:00:00Z"
    )
    domain = summary["domains"][0]
    assert domain["attention_episodes"] == 1
    assert domain["consecutive_attention_reports"] == 2
    assert domain["deltas_from_previous_report"]["unavailable_entity_count"] == 1


def test_resolved_then_returned_attention_is_recurring():
    history, _ = TRENDS.update_integration_trend_history(
        [], inventory(unavailable=2), "2026-11-01T00:00:00Z"
    )
    history, _ = TRENDS.update_integration_trend_history(
        history, inventory(), "2026-11-08T00:00:00Z"
    )
    history, summary = TRENDS.update_integration_trend_history(
        history, inventory(unavailable=1), "2026-11-15T00:00:00Z"
    )
    domain = summary["domains"][0]
    assert domain["attention_episodes"] == 2
    assert domain["recurring_attention"] is True
    assert domain["status"] == "attention"


def test_missing_domain_is_not_assumed_resolved():
    history, _ = TRENDS.update_integration_trend_history(
        [], inventory(unavailable=2), "2026-11-01T00:00:00Z"
    )
    empty = {"integration_domain_count": 0, "integrations": [], "inventory_truncated": False}
    history, summary = TRENDS.update_integration_trend_history(
        history, empty, "2026-11-08T00:00:00Z"
    )
    assert summary["domains"][0]["status"] == "not_in_latest_inventory"
    assert summary["domains"][0]["attention_episodes"] == 1


def test_history_is_bounded_and_contains_no_entity_identifiers():
    history = []
    for index in range(100):
        history, _ = TRENDS.update_integration_trend_history(
            history, inventory(unavailable=index % 2), f"2026-11-{index + 1:02d}T00:00:00Z"
        )
    assert len(history) == TRENDS.MAX_INTEGRATION_TREND_POINTS
    rendered = str(history)
    assert "sensor." not in rendered
    assert "entity_id" not in rendered
    assert "entry_id" not in rendered


def test_domain_inventory_truncation_is_reported():
    source = {
        "integration_domain_count": 300,
        "inventory_truncated": True,
        "integrations": [
            {"domain": f"domain_{index}", "setup_states": {}, "entity_count": 0}
            for index in range(300)
        ],
    }
    point = TRENDS.build_integration_trend_point(source, "2026-11-14T00:00:00Z")
    assert len(point["domains"]) == TRENDS.MAX_INTEGRATION_TREND_DOMAINS
    assert point["domains_truncated"] is True
    _, summary = TRENDS.update_integration_trend_history([], source, "2026-11-14T00:00:00Z")
    assert summary["inventory_truncated"] is True


def test_legacy_unknown_counts_do_not_produce_cross_classification_delta():
    legacy = {
        "timestamp": "2026-11-01T00:00:00Z",
        "domains": [{
            "domain": "mqtt", "config_entry_count": 1,
            "setup_error_count": 0, "setup_retry_count": 0,
            "entity_count": 10, "unavailable_entity_count": 0,
            "unknown_entity_count": 3, "attention": True,
            "signals": ["unknown_entities"],
        }],
    }
    _, summary = TRENDS.update_integration_trend_history(
        [legacy], inventory(unknown=0), "2026-11-08T00:00:00Z"
    )
    assert summary["domains"][0]["deltas_from_previous_report"]["unknown_entity_count"] is None


def test_missing_inventory_gap_does_not_create_false_recurrence():
    history, _ = TRENDS.update_integration_trend_history(
        [], inventory(unavailable=2), "2026-11-01T00:00:00Z"
    )
    empty = {"integration_domain_count": 0, "integrations": [], "inventory_truncated": False}
    history, _ = TRENDS.update_integration_trend_history(
        history, empty, "2026-11-08T00:00:00Z"
    )
    history, summary = TRENDS.update_integration_trend_history(
        history, inventory(unavailable=1), "2026-11-15T00:00:00Z"
    )
    domain = summary["domains"][0]
    assert domain["attention_episodes"] == 1
    assert domain["consecutive_attention_reports"] == 1
    assert domain["recurring_attention"] is False
