from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "custom_components" / "home_assistant_health_manager" / "repair_prompt.py"
SPEC = spec_from_file_location("health_manager_repair_prompt", MODULE_PATH)
PROMPT = module_from_spec(SPEC)
SPEC.loader.exec_module(PROMPT)


def test_prompt_contains_version_context_and_approval_workflow():
    prompt = PROMPT.build_repair_prompt(
        {
            "home_assistant_version": "2026.11.1",
            "platform_updates": {
                "core": {
                    "entity_present": True, "state": "on", "installed_version": "2026.10.0",
                    "latest_version": "2026.11.0", "update_available": True,
                    "release_summary": "Security and reliability fixes",
                    "release_url": "https://example.com/release",
                }
            },
            "entity_count": 100, "unavailable_entity_count": 2, "unknown_entity_count": 1,
            "failed_config_entry_count": 1, "failed_config_entry_domains": {"example_integration": 1},
            "config_entry_states": {"loaded": 20, "setup_error": 1},
        },
        {"level_counts": {"ERROR": 3}, "repeated_patterns": ["Example error occurred 3 times"]},
        [{
            "id": "failed_config_entries", "severity": "high",
            "title": "Integration setup failed", "detail": "One integration failed.",
            "suggested_action": "Inspect the integration logs.",
            "requires_user_approval": True, "automated_action_available": False,
        }],
        "2026-11-14T12:00:00+00:00",
    )
    assert "2026.11.1" in prompt
    assert "2026.10.0" in prompt and "2026.11.0" in prompt
    assert "https://example.com/release" in prompt
    assert "Wait for my approval" in prompt
    assert "configuration validation" in prompt
    assert "Do not make changes yet" in prompt


def test_prompt_excludes_raw_logs_entity_ids_and_clean_snapshot_pseudo_issue():
    prompt = PROMPT.build_repair_prompt(
        {
            "home_assistant_version": "2026.11.1",
            "entity_count": 1,
            "unavailable_entity_count": 0,
            "unknown_entity_count": 0,
            "failed_config_entry_count": 0,
            "failed_config_entry_domains": {},
            "platform_updates": {},
        },
        {"level_counts": {}, "repeated_patterns": []},
        [{
            "id": "no_rule_triggered", "severity": "info",
            "title": "No initial diagnostic rules were triggered",
            "detail": "No initial rules were triggered.",
            "suggested_action": "Continue monitoring.",
        }],
        "2026-11-14T12:00:00+00:00",
    )
    assert "sensor.private_entity" not in prompt
    assert "raw unredacted log" not in prompt
    assert "no_rule_triggered" not in prompt
    assert "not detected" in prompt
