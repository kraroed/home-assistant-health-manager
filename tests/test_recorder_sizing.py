from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

MODULE_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "home_assistant_health_manager"
    / "recorder_sizing.py"
)
SPEC = spec_from_file_location("health_manager_recorder_sizing", MODULE_PATH)
SIZING = module_from_spec(SPEC)
SPEC.loader.exec_module(SIZING)

RecordTooLargeError = SIZING.RecordTooLargeError
json_attribute_size = SIZING.json_attribute_size
pack_json_records = SIZING.pack_json_records


def test_pages_fit_complete_attribute_budget_and_preserve_every_record():
    records = [
        {"entity_id": f"sensor.test_{index}", "reason": "x" * 180}
        for index in range(40)
    ]
    metadata = {"page": 1, "note": "diagnostic details"}
    budget = 1_200

    pages = pack_json_records(
        records, metadata=metadata, max_bytes=budget
    )

    assert len(pages) > 1
    assert [item for page in pages for item in page] == records
    assert all(
        json_attribute_size({**metadata, "items": page}) <= budget
        for page in pages
    )


def test_unicode_is_measured_as_utf8_bytes():
    records = [{"description": "雪" * 100}]
    pages = pack_json_records(records, max_bytes=500)
    assert json_attribute_size({"items": pages[0]}) <= 500


def test_single_oversized_record_fails_instead_of_truncating():
    with pytest.raises(RecordTooLargeError, match="Record 0 requires"):
        pack_json_records([{"details": "x" * 2_000}], max_bytes=100)


def test_empty_input_returns_one_empty_page():
    assert pack_json_records([], max_bytes=100) == [[]]


def test_reserved_metadata_key_is_rejected():
    with pytest.raises(ValueError, match="reserved key"):
        pack_json_records([], metadata={"items": []})
