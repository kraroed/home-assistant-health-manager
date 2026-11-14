from custom_components.home_assistant_health_manager.redactor import redact_text


def test_common_identifiers_are_redacted():
    sample = (
        "person@example.com 192.168.1.20 AA:BB:CC:DD:EE:FF token=abc123456789 "
        "sensor.kitchen_temp /home/alex/config 43.5000,-112.0000 "
        "2001:db8:85a3::8a2e:370:7334"
    )
    cleaned, counts = redact_text(sample)
    for value in (
        "person@example.com", "192.168.1.20", "AA:BB:CC:DD:EE:FF",
        "sensor.kitchen_temp", "/home/alex", "43.5000,-112.0000",
        "2001:db8:85a3::8a2e:370:7334",
    ):
        assert value not in cleaned
    assert counts["email"] == 1
    assert counts["ipv4"] == 1
    assert counts["mac_address"] == 1
    assert counts["coordinates"] == 1
    assert counts["ipv6"] == 1
