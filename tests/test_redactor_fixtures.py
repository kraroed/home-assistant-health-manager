from custom_components.home_assistant_health_manager.redactor import redact_text


def test_common_identifiers_are_redacted():
    sample = "person@example.com 192.168.1.20 AA:BB:CC:DD:EE:FF token=abc123456789 sensor.kitchen_temp /home/alex/config"
    cleaned, counts = redact_text(sample)
    assert "person@example.com" not in cleaned
    assert "192.168.1.20" not in cleaned
    assert "AA:BB:CC:DD:EE:FF" not in cleaned
    assert "sensor.kitchen_temp" not in cleaned
    assert "/home/alex" not in cleaned
    assert counts["email"] == 1
    assert counts["ipv4"] == 1
    assert counts["mac_address"] == 1
