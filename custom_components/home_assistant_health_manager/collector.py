from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from homeassistant.config_entries import ConfigEntryState


def collect_snapshot(hass):
    """Collect in-memory Home Assistant data on the event-loop thread."""
    states = list(hass.states.async_all())
    unavailable = [state for state in states if state.state == "unavailable"]
    unknown = [state for state in states if state.state == "unknown"]
    entries = hass.config_entries.async_entries()
    return {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "home_assistant_version": hass.config.version,
        "entity_count": len(states),
        "unavailable_entity_count": len(unavailable),
        "unknown_entity_count": len(unknown),
        "unavailable_counts_by_domain": dict(Counter(state.domain for state in unavailable)),
        "unknown_counts_by_domain": dict(Counter(state.domain for state in unknown)),
        "entity_counts_by_domain": dict(Counter(state.domain for state in states)),
        "config_entry_count": len(entries),
        "config_entries_by_domain": dict(Counter(entry.domain for entry in entries)),
        "failed_config_entry_count": sum(entry.state is ConfigEntryState.SETUP_ERROR for entry in entries),
    }


def read_core_log(log_path, max_bytes=1_500_000):
    """Read a bounded Core log tail; safe to call in an executor thread."""
    path = Path(log_path)
    try:
        if not path.is_file():
            return None, "Core log file not found at the default path"
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > max_bytes:
                handle.seek(-max_bytes, 2)
            raw = handle.read(max_bytes)
        return raw.decode("utf-8", errors="replace"), None
    except OSError as err:
        return None, f"Core log could not be read ({type(err).__name__})"
