from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .investigation_history import build_selected_investigation

SENSORS = [
    ("status", "Health Status", None, None),
    ("health_overview", "Health Overview", None, None),
    ("unavailable_details", "Unavailable Details", None, None),
    ("unknown_details", "Unknown Details", None, None),
    ("integration_details", "Integration Details", None, None),
    ("investigation_details", "Investigation Details", None, None),
    ("diagnostic_details", "Diagnostic Details", None, None),
    *[(f"repair_plan_page_{page}", f"Repair Plan Page {page}", "items", SensorStateClass.MEASUREMENT) for page in range(1, 11)],
    ("active_issues", "Active Issues", "issues", SensorStateClass.MEASUREMENT),
    ("unavailable_entity_count", "Unavailable Entities", "entities", SensorStateClass.MEASUREMENT),
    ("tracked_unavailable_entity_count", "Tracked Unavailable Entities", "entities", SensorStateClass.MEASUREMENT),
    ("newly_unavailable_entity_count", "Newly Unavailable Entities", "entities", SensorStateClass.MEASUREMENT),
    ("persistent_unavailable_entity_count", "Persistent Unavailable Entities", "entities", SensorStateClass.MEASUREMENT),
    ("missing_tracked_entity_count", "Missing Tracked Entities", "entities", SensorStateClass.MEASUREMENT),
    ("unavailable_investigation_group_count", "Unavailable Investigation Groups", "groups", SensorStateClass.MEASUREMENT),
    ("availability_observation_event_count", "Unavailable Entity History Events", "events", SensorStateClass.MEASUREMENT),
    ("selected_unavailable_investigation", "Selected Unavailable Investigation", None, None),
    ("unavailable_investigation_count", "Unavailable Investigations", "investigations", SensorStateClass.MEASUREMENT),
    ("unavailable_investigations_needing_review", "Unavailable Investigations Needing Review", "investigations", SensorStateClass.MEASUREMENT),
    ("unavailable_investigations_in_progress", "Unavailable Investigations In Progress", "investigations", SensorStateClass.MEASUREMENT),
    ("unavailable_investigations_waiting", "Unavailable Investigations Waiting", "investigations", SensorStateClass.MEASUREMENT),
    ("unavailable_investigations_expected", "Unavailable Investigations Expected", "investigations", SensorStateClass.MEASUREMENT),
    ("unavailable_investigations_resolved", "Unavailable Investigations Resolved", "investigations", SensorStateClass.MEASUREMENT),
    ("actionable_unavailable_entity_count", "Actionable Unavailable Entities", "entities", SensorStateClass.MEASUREMENT),
    ("unknown_entity_count", "Unknown Entities", "entities", SensorStateClass.MEASUREMENT),
    ("actionable_unknown_entity_count", "Actionable Unknown Entities", "entities", SensorStateClass.MEASUREMENT),
    ("raw_actionable_unknown_entity_count", "Raw Actionable Unknown Entities", "entities", SensorStateClass.MEASUREMENT),
    ("classified_unknown_entity_count", "Classified Unknown Entities", "entities", SensorStateClass.MEASUREMENT),
    ("classified_unavailable_entity_count", "Classified Unavailable Entities", "entities", SensorStateClass.MEASUREMENT),
    ("classification_review_due_count", "Classification Reviews Due", "entities", SensorStateClass.MEASUREMENT),
    ("failed_config_entry_count", "Failed Integrations", "integrations", SensorStateClass.MEASUREMENT),
    ("config_entry_count", "Configured Integrations", "integrations", SensorStateClass.MEASUREMENT),
    ("integration_attention_domains", "Integration Attention Domains", "integrations", SensorStateClass.MEASUREMENT),
    ("integration_trend_domains", "Integration Trend Domains", "integrations", SensorStateClass.MEASUREMENT),
    ("tracked_issue_count", "Tracked Issues", "issues", SensorStateClass.MEASUREMENT),
    ("active_tracked_issue_count", "Active Tracked Issues", "issues", SensorStateClass.MEASUREMENT),
    ("resolved_tracked_issue_count", "Resolved Tracked Issues", "issues", SensorStateClass.MEASUREMENT),
    ("recurring_issue_count", "Recurring Issues", "issues", SensorStateClass.MEASUREMENT),
    ("active_recurring_issue_count", "Active Recurring Issues", "issues", SensorStateClass.MEASUREMENT),
    ("repair_plan_items", "Prioritized Repair Plan Items", "items", SensorStateClass.MEASUREMENT),
    ("repair_investigations", "Repair Investigations", "investigations", SensorStateClass.MEASUREMENT),
    ("selected_investigation", "Selected Investigation", None, None),
    ("core_update_status", "Core Update", None, None),
    ("supervisor_update_status", "Supervisor Update", None, None),
    ("operating_system_update_status", "Operating System Update", None, None),
    ("compatibility_status", "Compatibility Status", None, None),
    ("diagnostic_change_events", "Diagnostic Change Events", "events", SensorStateClass.MEASUREMENT),
    ("diagnostic_coverage", "Diagnostic Coverage", "%", SensorStateClass.MEASUREMENT),
    ("diagnostic_trend", "Diagnostic Trend", None, None),
    ("report_count", "Generated Reports", "reports", SensorStateClass.TOTAL_INCREASING),
]


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        HealthManagerSensor(coordinator, entry, key, name, unit, state_class)
        for key, name, unit, state_class in SENSORS
    )


class HealthManagerSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key, name, unit, state_class):
        super().__init__(coordinator)
        self.key = key
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = state_class

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        if self.key == "health_overview":
            return data.get("status", "unknown")
        if self.key == "compatibility_status":
            return data.get("compatibility_assessment", {}).get("overall_status", "not_assessed")
        if self.key == "integration_attention_domains":
            return data.get("integration_inventory", {}).get("attention_domain_count", 0)
        if self.key == "integration_trend_domains":
            return data.get("integration_trend_summary", {}).get("active_attention_domain_count", 0)
        if self.key == "repair_plan_items":
            return data.get("repair_plan", {}).get("item_count", 0)
        if self.key.startswith("repair_plan_page_"):
            page = int(self.key.rsplit("_", 1)[1])
            items = data.get("repair_plan", {}).get("items", [])
            return len(items[(page - 1) * 5:page * 5])
        if self.key.endswith("_details"):
            return "available"
        if self.key == "repair_investigations":
            return data.get("investigation_count", 0)
        if self.key == "availability_observation_event_count":
            return data.get("availability_observation_event_count", 0)
        if self.key == "selected_unavailable_investigation":
            selected_id = self.coordinator.selected_unavailable_investigation_id
            record = next(
                (item for item in data.get("unavailable_investigations", [])
                 if item.get("investigation_id") == selected_id),
                None,
            )
            return record.get("title") if record else "none_selected"
        if self.key == "selected_investigation":
            selected = build_selected_investigation(
                data, self.coordinator.selected_investigation_plan_id
            )["selected"]
            return selected.get("title") if selected else "none_selected"
        if self.key == "diagnostic_change_events":
            return data.get("diagnostic_change_history", {}).get("change_event_count", 0)
        if self.key == "diagnostic_coverage":
            return data.get("collection_coverage", {}).get("coverage_percent")
        if self.key == "diagnostic_trend":
            return data.get("diagnostic_trend", {}).get("overall_direction", "insufficient_data")
        if self.key.endswith("_update_status"):
            platform = self.key.removesuffix("_update_status")
            update = data.get("platform_updates", {}).get(platform, {})
            if not update.get("entity_present"):
                return "not_detected"
            if update.get("update_available") is True:
                return "update_available"
            if update.get("state") == "off":
                return "up_to_date"
            return update.get("state", "unknown")
        return data.get(self.key)

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}

        # Summary entities intentionally stay small. Detailed records live on
        # dedicated entities so Recorder can persist them independently.
        if self.key in {"status", "health_overview"}:
            return {
                "last_assessment": data.get("last_assessment"),
                "last_report": data.get("last_report"),
                "report_count": data.get("report_count", 0),
                "active_issues": data.get("active_issues", 0),
                "unavailable_entity_count": data.get("unavailable_entity_count", 0),
                "actionable_unavailable_entity_count": data.get("actionable_unavailable_entity_count", 0),
                "persistent_unavailable_entity_count": data.get("persistent_unavailable_entity_count", 0),
                "unknown_entity_count": data.get("unknown_entity_count", 0),
                "actionable_unknown_entity_count": data.get("actionable_unknown_entity_count", 0),
                "failed_config_entry_count": data.get("failed_config_entry_count", 0),
                "classification_review_due_count": data.get("classification_review_due_count", 0),
                "config_entry_count": data.get("config_entry_count", 0),
                "collection_coverage": {
                    "coverage_percent": data.get("collection_coverage", {}).get("coverage_percent")
                },
                "compatibility_assessment": {
                    "overall_status": data.get("compatibility_assessment", {}).get("overall_status", "not_assessed")
                },
                "diagnostic_trend": {
                    "overall_direction": data.get("diagnostic_trend", {}).get("overall_direction", "insufficient_data")
                },
                "platform_update_states": {
                    key: value.get("state", "unknown")
                    for key, value in data.get("platform_updates", {}).items()
                    if isinstance(value, dict)
                },
                "detail_entities": [
                    "sensor.unavailable_details", "sensor.unknown_details",
                    "sensor.integration_details", "sensor.investigation_details",
                    "sensor.diagnostic_details",
                ],
                "repair_plan_item_count": data.get("repair_plan", {}).get("item_count", 0),
                "repair_plan_page_count": min(
                    10, (len(data.get("repair_plan", {}).get("items", [])) + 4) // 5
                ),
            }

        if self.key == "unavailable_details":
            return {
                "newly_unavailable_entity_ids": data.get("newly_unavailable_entity_ids", []),
                "persistent_unavailable_entity_ids": data.get("persistent_unavailable_entity_ids", []),
                "missing_tracked_entity_ids": data.get("missing_tracked_entity_ids", []),
                "unavailable_investigation_groups": data.get("unavailable_investigation_groups", []),
                "unavailable_entity_count": data.get("unavailable_entity_count", 0),
                "tracked_unavailable_entity_count": data.get("tracked_unavailable_entity_count", 0),
                "newly_unavailable_entity_count": data.get("newly_unavailable_entity_count", 0),
                "persistent_unavailable_entity_count": data.get("persistent_unavailable_entity_count", 0),
                "missing_tracked_entity_count": data.get("missing_tracked_entity_count", 0),
                "unavailable_investigation_group_count": data.get("unavailable_investigation_group_count", 0),
            }
        if self.key == "unknown_details":
            return {
                "entity_classification_counts": data.get("entity_classification_counts", {}),
                "unknown_counts_by_domain": data.get("unknown_counts_by_domain", {}),
                "classification_review_due_entities": data.get("classification_review_due_entities", []),
                "unknown_entity_count": data.get("unknown_entity_count", 0),
                "actionable_unknown_entity_count": data.get("actionable_unknown_entity_count", 0),
                "raw_actionable_unknown_entity_count": data.get("raw_actionable_unknown_entity_count", 0),
                "classified_unknown_entity_count": data.get("classified_unknown_entity_count", 0),
                "classification_review_due_count": data.get("classification_review_due_count", 0),
            }
        if self.key == "integration_details":
            return {
                "integration_inventory": data.get("integration_inventory", {}),
                "failed_config_entry_domains": data.get("failed_config_entry_domains", {}),
                "config_entry_states": data.get("config_entry_states", {}),
                "integration_trend_summary": data.get("integration_trend_summary", {}),
                "config_entry_count": data.get("config_entry_count", 0),
                "failed_config_entry_count": data.get("failed_config_entry_count", 0),
                "integration_attention_domains": data.get("integration_inventory", {}).get("attention_domains", []),
            }
        if self.key == "investigation_details":
            return {
                "unavailable_investigations": data.get("unavailable_investigations", []),
                "unavailable_investigation_count": data.get("unavailable_investigation_count", 0),
                "unavailable_investigation_status_counts": data.get("unavailable_investigation_status_counts", {}),
                "unavailable_investigations_needing_review": data.get("unavailable_investigations_needing_review", 0),
                "unavailable_investigations_in_progress": data.get("unavailable_investigations_in_progress", 0),
                "unavailable_investigations_waiting": data.get("unavailable_investigations_waiting", 0),
                "unavailable_investigations_expected": data.get("unavailable_investigations_expected", 0),
                "unavailable_investigations_resolved": data.get("unavailable_investigations_resolved", 0),
            }
        if self.key == "diagnostic_details":
            return {
                "platform_updates": data.get("platform_updates", {}),
                "compatibility_assessment": data.get("compatibility_assessment", {}),
                "diagnostic_change_history": data.get("diagnostic_change_history", {}),
                "collection_coverage": data.get("collection_coverage", {}),
                "diagnostic_trend": data.get("diagnostic_trend", {}),
                "integration_trend_summary": data.get("integration_trend_summary", {}),
                "report_count": data.get("report_count", 0),
                "last_ai_repair_prompt_path": data.get("last_ai_repair_prompt_path"),
                "repair_investigations": data.get("investigations", []),
                "investigation_status_counts": data.get("investigation_status_counts", {}),
                "recurring_issues": data.get("recurring_issues", []),
                "recurring_issue_count": data.get("recurring_issue_count", 0),
                "active_recurring_issue_count": data.get("active_recurring_issue_count", 0),
                "entity_count": data.get("entity_count"),
                "entity_counts_by_domain": data.get("entity_counts_by_domain", {}),
                "unavailable_counts_by_domain": data.get("unavailable_counts_by_domain", {}),
                "unknown_counts_by_domain": data.get("unknown_counts_by_domain", {}),
                "actionable_unknown_counts_by_domain": data.get("actionable_unknown_counts_by_domain", {}),
            }
        if self.key == "repair_plan_items":
            plan = data.get("repair_plan", {})
            return {
                "item_count": plan.get("item_count", 0),
                "page_count": min(10, (len(plan.get("items", [])) + 4) // 5),
                "priority_order": plan.get("priority_order", []),
                "omitted_item_count": plan.get("omitted_item_count", 0),
                "scope_note": plan.get("scope_note"),
                "detail_entities": [
                    f"sensor.repair_plan_page_{page}"
                    for page in range(1, min(10, (len(plan.get("items", [])) + 4) // 5) + 1)
                ],
            }
        if self.key.startswith("repair_plan_page_"):
            page = int(self.key.rsplit("_", 1)[1])
            plan = data.get("repair_plan", {})
            items = plan.get("items", [])
            return {
                "items": items[(page - 1) * 5:page * 5],
                "page": page,
                "page_size": 5,
                "total_items": plan.get("item_count", 0),
                "note": "All plan entries are advisory; each repair requires explicit user approval.",
            }
        if self.key == "integration_trend_domains":
            return data.get("integration_trend_summary", {})
        if self.key == "repair_investigations":
            return {
                "investigations": data.get("investigations", []),
                "status_counts": data.get("investigation_status_counts", {}),
                "retained_limit": 50,
            }
        if self.key == "selected_investigation":
            selected_id = self.coordinator.selected_investigation_plan_id
            selected_data = build_selected_investigation(data, selected_id)
            return {
                **selected_data,
                "selection_required": selected_data["selected"] is None,
                "selection_stale": selected_id is not None and selected_data["selected"] is None,
                "scope_note": "Finding details come from the latest generated repair plan. Investigation status is a user tracking label, not verification.",
            }
        if self.key == "availability_observation_event_count":
            return {
                "events": data.get("availability_observation_events", []),
                "retained_limit": 100,
                "note": "Recent availability transitions and user investigation status changes. A missing entity is not automatically treated as recovered.",
            }
        if self.key == "selected_unavailable_investigation":
            selected_id = self.coordinator.selected_unavailable_investigation_id
            record = next(
                (item for item in data.get("unavailable_investigations", [])
                 if item.get("investigation_id") == selected_id),
                None,
            )
            return {
                "selected_investigation_id": selected_id,
                "investigation": record,
                "selection_required": record is None,
                "note": "Status and notes are user-managed tracking metadata. Expected and Resolved never classify or suppress entities.",
            }
        if self.key == "integration_attention_domains":
            return {
                "domains": data.get("integration_inventory", {}).get("attention_domains", []),
                "truncated": data.get("integration_inventory", {}).get("attention_domains_truncated", False),
            }
        if self.key.endswith("_update_status"):
            platform = self.key.removesuffix("_update_status")
            return data.get("platform_updates", {}).get(platform, {})
        return {}
