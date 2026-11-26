"""Focused regression tests for dashboard entity-classification service safety."""
import ast
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

ROOT = Path(__file__).parents[1]
INTEGRATION = ROOT / "custom_components" / "home_assistant_health_manager"
MODULE_PATH = INTEGRATION / "entity_classifications.py"
SPEC = spec_from_file_location("health_manager_classification_contract", MODULE_PATH)
CLASSIFICATIONS = module_from_spec(SPEC)
SPEC.loader.exec_module(CLASSIFICATIONS)


def test_service_target_requires_exactly_one_non_empty_target():
    valid_single = {"entity_id": "sensor.one"}
    valid_bulk = {"entity_ids": ["sensor.one", "sensor.two"]}
    assert CLASSIFICATIONS.validate_classification_target(valid_single) is valid_single
    assert CLASSIFICATIONS.validate_classification_target(valid_bulk) is valid_bulk

    for invalid in (
        {},
        {"entity_id": " "},
        {"entity_ids": []},
        {"entity_id": "sensor.one", "entity_ids": ["sensor.two"]},
    ):
        try:
            CLASSIFICATIONS.validate_classification_target(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid service target accepted: {invalid!r}")


def test_bulk_targets_are_trimmed_deduplicated_and_protect_saved_records():
    stored = CLASSIFICATIONS.set_entity_classification(
        {}, "sensor.saved", "expected", "Already documented."
    )
    assert CLASSIFICATIONS.validate_bulk_classification_targets(
        stored, [" sensor.new ", "sensor.new", "sensor.other"]
    ) == ["sensor.new", "sensor.other"]

    try:
        CLASSIFICATIONS.validate_bulk_classification_targets(
            stored, ["sensor.new", "sensor.saved"]
        )
    except ValueError as err:
        assert "cannot overwrite existing saved classifications" in str(err)
        assert "sensor.saved" in str(err)
    else:
        raise AssertionError("bulk operation overwrote a saved classification")

    assert CLASSIFICATIONS.validate_bulk_classification_targets(
        stored, ["sensor.saved"], allow_existing=True
    ) == ["sensor.saved"]


def test_bulk_update_is_all_or_nothing_and_does_not_mutate_input_store():
    stored = CLASSIFICATIONS.set_entity_classification(
        {}, "sensor.existing", "expected", "Keep this record."
    )
    before = repr(stored)
    try:
        CLASSIFICATIONS.set_entity_classifications(
            stored,
            ["sensor.new", "sensor.other"],
            "not_a_classification",
            "Invalid choice.",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("invalid bulk classification should fail")
    assert repr(stored) == before
    assert set(stored["entities"]) == {"sensor.existing"}


def _function(tree, name):
    return next(
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    )


def test_coordinator_bulk_save_validates_under_lock_and_commits_after_storage():
    tree = ast.parse((INTEGRATION / "coordinator.py").read_text(encoding="utf-8"))
    coordinator = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "HealthManagerCoordinator"
    )
    method = next(
        node for node in coordinator.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "async_set_entity_classifications"
    )
    source = ast.get_source_segment(
        (INTEGRATION / "coordinator.py").read_text(encoding="utf-8"), method
    )
    assert "async with self._state_lock" in source
    assert source.index("validate_bulk_classification_targets") < source.index(
        "updated = set_entity_classifications("
    )
    assert source.index("await self.classification_store.async_save(updated)") < source.index(
        "self.entity_classifications = updated"
    )
    assert "allow_existing=False" in source


def test_single_entity_path_explicitly_allows_intentional_existing_record_edits():
    tree = ast.parse((INTEGRATION / "coordinator.py").read_text(encoding="utf-8"))
    method = _function(tree, "async_set_entity_classification")
    source = ast.get_source_segment(
        (INTEGRATION / "coordinator.py").read_text(encoding="utf-8"), method
    )
    assert "allow_existing=True" in source
    assert "async_set_entity_classifications" in source


def test_service_schema_and_handler_enforce_single_or_bulk_routing():
    source = (INTEGRATION / "services.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    handler = _function(tree, "set_entity_classification_service")
    handler_source = ast.get_source_segment(source, handler)
    assert "if entity_ids:" in handler_source
    assert "async_set_entity_classifications" in handler_source
    assert "async_set_entity_classification" in handler_source
    assert "return" in handler_source
    assert "_validate_classification_target" in source
    assert "validate_classification_target(data)" in source
    assert "vol.All(" in source
