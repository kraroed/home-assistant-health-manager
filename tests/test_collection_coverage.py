from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "custom_components" / "home_assistant_health_manager" / "collection_coverage.py"
SPEC = spec_from_file_location("health_manager_collection_coverage", MODULE_PATH)
COVERAGE = module_from_spec(SPEC)
SPEC.loader.exec_module(COVERAGE)


def _snapshot():
    return {
        "entity_count": 10,
        "config_entry_count": 4,
        "platform_updates": {},
        "update_entity_inventory": {},
        "integration_inventory": {},
    }


def test_complete_source_coverage_does_not_claim_system_health():
    result = COVERAGE.build_collection_coverage(_snapshot(), "collected")
    assert result["overall_status"] == "complete"
    assert result["coverage_percent"] == 100
    assert result["unavailable_source_count"] == 0
    assert "does not measure system health" in result["scope_note"]


def test_unavailable_core_log_reduces_coverage():
    result = COVERAGE.build_collection_coverage(_snapshot(), "unavailable")
    assert result["overall_status"] == "partial"
    assert result["coverage_percent"] < 100
    log = next(item for item in result["sources"] if item["source"] == "core_log")
    assert log["status"] == "unavailable"


def test_not_checked_sources_are_not_counted_as_failures():
    result = COVERAGE.build_collection_coverage(_snapshot())
    assert result["overall_status"] == "complete"
    assert result["coverage_percent"] == 100
    assert result["not_assessed_source_count"] == 1


def test_missing_multiple_sources_is_limited_not_healthy():
    result = COVERAGE.build_collection_coverage({"entity_count": 3}, "not_enabled")
    assert result["overall_status"] == "partial"
    assert result["unavailable_source_count"] == 4
    assert result["not_assessed_source_count"] == 1
