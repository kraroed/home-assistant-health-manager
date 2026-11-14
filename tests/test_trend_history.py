from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "custom_components" / "home_assistant_health_manager" / "trend_history.py"
SPEC = spec_from_file_location("health_manager_trend_history", MODULE_PATH)
TRENDS = module_from_spec(SPEC)
SPEC.loader.exec_module(TRENDS)


def sample(unavailable=4, coverage=100, errors=2):
    return {
        "entity_count": 200,
        "unavailable_entity_count": unavailable,
        "unknown_entity_count": 1,
        "failed_config_entry_count": 0,
        "collection_coverage": {"coverage_percent": coverage},
    }, {"available": True, "level_counts": {"ERROR": errors, "WARNING": 3}}, {"overall_status": "no_platform_update_reported"}


def test_first_sample_has_insufficient_data():
    snapshot, analysis, compatibility = sample()
    history, summary = TRENDS.update_trend_history([], snapshot, analysis, compatibility, "2026-11-14T00:00:00Z")
    assert len(history) == 1
    assert summary["overall_direction"] == "insufficient_data"


def test_unavailable_and_error_count_changes_are_compared():
    first, analysis1, compatibility = sample(unavailable=5, errors=4)
    history, _ = TRENDS.update_trend_history([], first, analysis1, compatibility, "2026-11-14T00:00:00Z")
    second, analysis2, _ = sample(unavailable=2, errors=1, coverage=100)
    history, summary = TRENDS.update_trend_history(history, second, analysis2, compatibility, "2026-11-21T00:00:00Z")
    assert summary["metrics"]["unavailable_entity_count"]["direction"] == "improved"
    assert summary["metrics"]["core_log_error_count"]["direction"] == "improved"
    assert summary["overall_direction"] == "improving"


def test_worsening_and_mixed_directions_are_distinguished():
    first, analysis, compatibility = sample(unavailable=1, coverage=90)
    history, _ = TRENDS.update_trend_history([], first, analysis, compatibility, "2026-11-14T00:00:00Z")
    second, analysis2, _ = sample(unavailable=3, coverage=100)
    history, summary = TRENDS.update_trend_history(history, second, analysis2, compatibility, "2026-11-21T00:00:00Z")
    assert summary["metrics"]["unavailable_entity_count"]["direction"] == "worsened"
    assert summary["overall_direction"] == "mixed"


def test_history_is_bounded_and_deduplicates_identical_consecutive_points():
    history = []
    snapshot, analysis, compatibility = sample()
    for index in range(110):
        snapshot["unavailable_entity_count"] = index
        history, _ = TRENDS.update_trend_history(history, snapshot, analysis, compatibility, f"2026-11-{index:02d}T00:00:00Z")
    assert len(history) <= TRENDS.MAX_TREND_POINTS
    latest, _ = TRENDS.update_trend_history(history, snapshot, analysis, compatibility, "2026-11-109T00:00:00Z")
    assert latest == history



def test_missing_metric_values_remain_insufficient_and_compatibility_change_is_visible():
    first = {
        "collection_coverage": {},
    }
    second = {
        "collection_coverage": {},
    }
    empty_analysis = {"available": False, "level_counts": {}}
    first_compat = {"overall_status": "insufficient_platform_data"}
    second_compat = {"overall_status": "existing_issues_require_review"}
    history, _ = TRENDS.update_trend_history([], first, empty_analysis, first_compat, "2026-11-14T00:00:00Z")
    history, summary = TRENDS.update_trend_history(history, second, empty_analysis, second_compat, "2026-11-21T00:00:00Z")
    assert summary["overall_direction"] == "insufficient_data"
    assert summary["compatibility_status"]["changed"] is True
    assert summary["compatibility_status"]["current"] == "existing_issues_require_review"



def test_unavailable_core_log_is_not_recorded_as_zero_errors():
    snapshot, analysis, compatibility = sample()
    analysis["available"] = False
    history, _ = TRENDS.update_trend_history([], snapshot, analysis, compatibility, "2026-11-14T00:00:00Z")
    snapshot2, analysis2, _ = sample()
    analysis2["available"] = False
    history, summary = TRENDS.update_trend_history(history, snapshot2, analysis2, compatibility, "2026-11-21T00:00:00Z")
    assert history[-1]["core_log_error_count"] is None
    assert summary["metrics"]["core_log_error_count"]["direction"] == "insufficient_data"
    assert summary["overall_direction"] == "improving"  # unavailable/unknown counts decreased in sample()
