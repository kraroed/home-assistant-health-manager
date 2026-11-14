"""Read Home Assistant platform update entities without Supervisor API access."""

PLATFORMS = {
    "core": ("home assistant core", "home_assistant_core"),
    "supervisor": ("home assistant supervisor", "home_assistant_supervisor"),
    "operating_system": ("home assistant operating system", "home_assistant_operating_system"),
}


def collect_platform_updates(states):
    """Return a bounded inventory of Core, Supervisor, and OS update entities."""
    result = {
        key: {
            "entity_present": False,
            "state": "missing",
            "installed_version": None,
            "latest_version": None,
            "update_available": None,
            "in_progress": None,
            "release_summary": None,
            "release_url": None,
        }
        for key in PLATFORMS
    }
    for state in states:
        if getattr(state, "domain", None) != "update":
            continue
        entity_id = getattr(state, "entity_id", "")
        attributes = getattr(state, "attributes", {}) or {}
        identity = " ".join((
            entity_id.replace(".", " ").replace("_", " "),
            str(attributes.get("title") or ""),
            str(attributes.get("friendly_name") or ""),
        )).casefold()
        for key, (title, entity_fragment) in PLATFORMS.items():
            if title in identity or entity_fragment.replace("_", " ") in identity:
                result[key] = {
                    "entity_present": True,
                    "state": state.state,
                    "installed_version": attributes.get("installed_version"),
                    "latest_version": attributes.get("latest_version"),
                    "update_available": state.state == "on",
                    "in_progress": attributes.get("in_progress"),
                    "release_summary": attributes.get("release_summary"),
                    "release_url": attributes.get("release_url"),
                }
                break
    return result
