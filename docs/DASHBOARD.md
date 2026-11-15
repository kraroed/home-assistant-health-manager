# Home Assistant Health Manager dashboard

This is an optional Lovelace dashboard built entirely from Home Assistant's native Markdown, Entities, and History Graph cards. It does not require a frontend resource, JavaScript module, external service, or additional HACS repository.

Add a **Manual card** to a dashboard and paste the YAML below. If Home Assistant assigned different entity IDs on your installation, select the matching entities from the entity picker and replace the example IDs.

```yaml
type: vertical-stack
cards:
  - type: markdown
    title: Home Assistant Health
    content: |
      ## {{ states('sensor.health_status') | title }}

      **Diagnostic trend:** {{ states('sensor.diagnostic_trend') | replace('_', ' ') | title }}

      **Diagnostic coverage:** {{ states('sensor.diagnostic_coverage') }}%

      **Compatibility:** {{ states('sensor.compatibility_status') | replace('_', ' ') | title }}

      _Coverage describes collected diagnostic sources; it is not a health score._
  - type: entities
    title: Current diagnostics
    show_header_toggle: false
    entities:
      - entity: sensor.active_issues
        name: Active issues
      - entity: sensor.unavailable_entities
        name: Unavailable entities
      - entity: sensor.unknown_entities
        name: Unknown entities
      - entity: sensor.failed_integrations
        name: Failed integrations
      - entity: sensor.integration_attention_domains
        name: Integration domains needing attention
      - entity: sensor.integration_trend_domains
        name: Integration domains with active trend attention
      - entity: sensor.recurring_issues
        name: Recurring issues
      - entity: sensor.active_recurring_issues
        name: Active recurring issues
      - entity: sensor.prioritized_repair_plan_items
        name: Prioritized repair plan items
      - entity: select.home_assistant_health_manager_generate_focused_repair_prompt
        name: Generate focused AI investigation prompt
      - entity: sensor.diagnostic_coverage
        name: Diagnostic coverage
      - entity: sensor.diagnostic_trend
        name: Diagnostic trend
      - entity: sensor.compatibility_status
        name: Compatibility status
  - type: history-graph
    title: Issue counts
    hours_to_show: 168
    refresh_interval: 60
    entities:
      - entity: sensor.active_issues
        name: Active issues
      - entity: sensor.unavailable_entities
        name: Unavailable
      - entity: sensor.unknown_entities
        name: Unknown
      - entity: sensor.failed_integrations
        name: Failed integrations
  - type: history-graph
    title: Diagnostic coverage
    hours_to_show: 168
    refresh_interval: 60
    entities:
      - entity: sensor.diagnostic_coverage
        name: Sources collected (%)
```

## Reading the dashboard

- The trend sensor compares the latest generated report with the preceding report. Its first state is `insufficient_data`.
- Issue-count and coverage history graphs use Home Assistant's recorder. They show recorded state changes; they are not a substitute for the report-time trend history.
- The trend history is retained locally by the integration for up to 90 report samples. The dashboard graphs follow your Home Assistant recorder retention settings.
- The compatibility sensor is a limited triage signal, not a promise that an upgrade is safe.
- A low or partial coverage result means some sources were unavailable. It must not be interpreted as proof of a healthy system.

The diagnostic sensors are read-only. The focused-prompt select is an explicit user-triggered action that only writes a local Markdown prompt and fires an event; it does not invoke repair, update, restart, or configuration changes.


The `Integration Attention Domains` sensor counts provider integrations with setup errors/retries or unavailable/unknown registered entities. Its attributes on the sensor and Health Status entity show a bounded, severity-ranked domain list. This is a triage correlation, not proof of a shared root cause.

The `Integration Trend Domains` sensor counts provider domains currently in an attention state. Its attributes show report-to-report counts, changes from the previous report, consecutive attention reports, and distinct attention episodes. A domain absent from a later inventory is marked not present rather than assumed resolved. History is local and bounded to 90 generated reports.

Recurring issue sensors count problems that were detected, resolved, and later detected again. The Health Status sensor attributes include the bounded recurrence list with occurrence count and first/last-seen timestamps. Only currently active recurring issues create an additional advisory recommendation; resolved recurring issues remain visible as history. These recommendations never execute repairs.

The `Prioritized Repair Plan Items` sensor counts the current report's deduplicated, severity-sorted plan. Its attributes expose each plan item, linked recommendation IDs, and related log/trend evidence. The Health Status sensor also includes the plan. The plan is populated when a diagnostic report is generated; it is advisory and never performs repairs.


## Generate a focused investigation prompt

After a report is generated, open the `Prioritized Repair Plan Items` sensor and copy the exact `plan_id` for the item you want to investigate. For example, if the selected item has `plan_id: integration_mqtt`, call the service:

```yaml
action: home_assistant_health_manager.generate_focused_repair_prompt
data:
  plan_id: integration_mqtt
```

Replace the example ID with the exact ID from your sensor attributes. Listen for the `home_assistant_health_manager_focused_repair_prompt_created` event; its `prompt_path` points to the Markdown file in `/config/health_manager/reports`. The service does not modify Home Assistant configuration or perform repairs.


## Generate a focused investigation prompt from the dashboard

After generating a diagnostic report, use the **Generate focused AI investigation prompt** select entity in the Current diagnostics card:

1. Open the dropdown.
2. Choose the finding to investigate. Options show severity, title, and exact plan ID.
3. Selecting an option immediately creates a separate Markdown prompt in `/config/health_manager/reports`.
4. Listen for `home_assistant_health_manager_focused_repair_prompt_created` to receive the selected `plan_id` and `prompt_path`.

The selector is populated from the latest report. Generate or refresh a report if the list is empty or a finding has changed. An obsolete selection is rejected rather than silently mapped to another issue. Selecting an item only creates a local prompt; it does not modify Home Assistant configuration or perform repairs.

For automations or scripts, the `home_assistant_health_manager.generate_focused_repair_prompt` service remains available with the exact `plan_id` from the repair-plan sensor attributes.
