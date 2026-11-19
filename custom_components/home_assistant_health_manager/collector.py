from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import __version__ as HOME_ASSISTANT_VERSION
from homeassistant.helpers import entity_registry as er

from .integration_inventory import collect_integration_inventory, is_actionable_unknown_domain
from .update_inventory import collect_platform_updates
from .update_entity_inventory import collect_update_entity_inventory
from .entity_classifications import NON_ACTIONABLE_CLASSIFICATIONS, get_review_due_entities


def collect_snapshot(hass, entity_classifications=None):
    """Collect raw inventory plus explicitly user-classified diagnostic views."""
    states = list(hass.states.async_all())
    unavailable = [state for state in states if state.state == "unavailable"]
    unknown = [state for state in states if state.state == "unknown"]
    records = (entity_classifications or {}).get("entities", {})
    records = records if isinstance(records, dict) else {}

    def classification_for(state):
        record = records.get(state.entity_id, {})
        value = record.get("classification") if isinstance(record, dict) else None
        return value if isinstance(value, str) else None

    # Raw unknown/unavailable inventories are never reduced by classifications.
    raw_actionable_unknown = [
        state for state in unknown if is_actionable_unknown_domain(state.domain)
    ]
    actionable_unknown = [
        state for state in unknown
        if classification_for(state) == "actionable"
        or (
            is_actionable_unknown_domain(state.domain)
            and classification_for(state) not in NON_ACTIONABLE_CLASSIFICATIONS
        )
    ]
    actionable_unavailable = [
        state for state in unavailable
        if classification_for(state) not in NON_ACTIONABLE_CLASSIFICATIONS
    ]
    classified_unknown = [state for state in unknown if classification_for(state)]
    classified_unavailable = [state for state in unavailable if classification_for(state)]
    classification_counts = Counter(
        classification_for(state) for state in states if classification_for(state)
    )
    entries = hass.config_entries.async_entries()
    entity_registry = er.async_get(hass)
    failed_entries = [
        entry for entry in entries
        if entry.state is ConfigEntryState.SETUP_ERROR
    ]
    entry_states = Counter(entry.state.value for entry in entries)
    review_due = get_review_due_entities(entity_classifications or {})
    return {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "home_assistant_version": HOME_ASSISTANT_VERSION,
        "platform_updates": collect_platform_updates(states),
        "update_entity_inventory": collect_update_entity_inventory(states, entity_registry, hass.config_entries),
        "integration_inventory": collect_integration_inventory(entries, entity_registry, states),
        "entity_count": len(states),
        "unavailable_entity_count": len(unavailable),
        "actionable_unavailable_entity_count": len(actionable_unavailable),
        "unknown_entity_count": len(unknown),
        "raw_actionable_unknown_entity_count": len(raw_actionable_unknown),
        "actionable_unknown_entity_count": len(actionable_unknown),
        "expected_unknown_entity_count": len(unknown) - len(actionable_unknown),
        "classified_unknown_entity_count": len(classified_unknown),
        "classified_unavailable_entity_count": len(classified_unavailable),
        "entity_classification_counts": dict(classification_counts),
        "classification_review_due_count": len(review_due),
        "classification_review_due_entities": review_due,
        "unavailable_counts_by_domain": dict(Counter(state.domain for state in unavailable)),
        "unknown_counts_by_domain": dict(Counter(state.domain for state in unknown)),
        "actionable_unknown_counts_by_domain": dict(Counter(state.domain for state in actionable_unknown)),
        "entity_counts_by_domain": dict(Counter(state.domain for state in states)),
        "config_entry_count": len(entries),
        "config_entries_by_domain": dict(Counter(entry.domain for entry in entries)),
        "config_entry_states": dict(entry_states),
        "failed_config_entry_count": len(failed_entries),
        "failed_config_entry_domains": dict(Counter(entry.domain for entry in failed_entries)),
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
