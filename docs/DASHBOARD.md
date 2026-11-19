# Home Assistant Health Manager dashboard

This is an optional Lovelace dashboard built entirely from Home Assistant's native Markdown, Entities, and History Graph cards. It does not require a frontend resource, JavaScript module, external service, or additional HACS repository.

Add a **Manual card** to a dashboard and paste the YAML below. If Home Assistant assigned different entity IDs on your installation, select the matching entities from the entity picker and replace the example IDs.

```yaml
type: vertical-stack
cards:
  - type: markdown
    title: Home Assistant Health — At a Glance
    content: |
      ## {{ states('sensor.health_status') | title }}

      **Active issues:** {{ states('sensor.active_issues') }}
      **Unavailable:** {{ states('sensor.unavailable_entities') }}
      **Unknown (actionable / raw):** {{ states('sensor.actionable_unknown_entities') }} / {{ states('sensor.unknown_entities') }}
      **Failed integrations:** {{ states('sensor.failed_integrations') }}

      **Platform updates:** Core {{ states('sensor.core_update') | replace('_', ' ') }}, Supervisor {{ states('sensor.supervisor_update') | replace('_', ' ') }}, OS {{ states('sensor.operating_system_update') | replace('_', ' ') }}

      **Diagnostic trend:** {{ states('sensor.diagnostic_trend') | replace('_', ' ') | title }}
      **Diagnostic coverage:** {{ states('sensor.diagnostic_coverage') }}%
      **Compatibility:** {{ states('sensor.compatibility_status') | replace('_', ' ') | title }}

      {% set attention = state_attr('sensor.health_status', 'integration_attention_domains') or [] %}
      **Integration attention areas**
      {% for item in attention[:5] %}
      - **{{ item.domain }}** ({{ item.severity | upper }}) — {{ item.unavailable_entity_count }} unavailable, {{ item.actionable_unknown_entity_count }} actionable unknown
      {% else %}
      - No integration attention areas were reported
      {% endfor %}

      _Raw unknown counts include stateless buttons. Actionable unknown counts exclude buttons. Coverage describes collected diagnostic sources; it is not a health score._
  - type: entities
    title: Current diagnostics
    show_header_toggle: false
    entities:
      - entity: sensor.active_issues
        name: Active issues
      - entity: sensor.unavailable_entities
        name: Unavailable entities
      - entity: sensor.unknown_entities
        name: Unknown entities (raw)
      - entity: sensor.actionable_unknown_entities
        name: Actionable unknown entities
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
      - entity: sensor.repair_investigations
        name: Focused repair investigations
      - entity: sensor.home_assistant_health_manager_selected_investigation
        name: Selected investigation details
      - entity: select.home_assistant_health_manager_generate_focused_repair_prompt
        name: Generate focused AI investigation prompt
      - entity: select.home_assistant_health_manager_investigation_to_update
        name: Investigation to update
      - entity: select.home_assistant_health_manager_investigation_status
        name: Investigation status
      - entity: sensor.classification_reviews_due
        name: Entity classifications needing review
      - entity: select.home_assistant_health_manager_entity_classification_to_review
        name: Entity classification to review
      - entity: select.home_assistant_health_manager_confirm_entity_classification_review
        name: Confirm selected classification review
      - entity: sensor.diagnostic_coverage
        name: Diagnostic coverage
      - entity: sensor.diagnostic_trend
        name: Diagnostic trend
      - entity: sensor.compatibility_status
        name: Compatibility status
  - type: markdown
    title: Selected investigation details
    content: |
      {% set selected = state_attr('sensor.home_assistant_health_manager_selected_investigation', 'selected') %}
      {% set finding = state_attr('sensor.home_assistant_health_manager_selected_investigation', 'finding') %}
      {% if selected %}
      ## {{ selected.title }}

      **Status:** {{ selected.status | replace('_', ' ') | title }}

      **Severity:** {{ selected.severity | upper }}

      **Plan ID:** `{{ selected.plan_id }}`

      **Prompt generated:** {{ selected.last_generated_at }}

      **Prompt generations:** {{ selected.generation_count }}

      **Prompt file:** `{{ selected.prompt_path }}`

      {% if finding %}
      ### Current finding details

      **Related recommendations:** {{ finding.recommendation_ids | join(', ') }}

      **Suggested next steps**
      {% for action in finding.suggested_actions %}
      - {{ action }}
      {% endfor %}

      **Evidence**
      {% for evidence in finding.evidence %}
      - **{{ evidence.type | replace('_', ' ') | title }}:** {{ evidence }}
      {% else %}
      - No additional structured evidence is attached to this finding.
      {% endfor %}
      {% else %}
      The investigation is in history, but its finding is not in the latest repair plan. The history and prompt file remain available.
      {% endif %}
      {% else %}
      {% if state_attr('sensor.home_assistant_health_manager_selected_investigation', 'selection_stale') %}
      The previously selected investigation is no longer in the retained history. Choose a current investigation in the **Investigation to Update** dropdown.
      {% else %}
      Choose an investigation in the **Investigation to Update** dropdown to see its details here.
      {% endif %}
      {% endif %}
  - type: markdown
    title: Repair investigation history
    content: |
      {% set investigations = state_attr('sensor.home_assistant_health_manager_repair_investigations', 'investigations') or [] %}
      {% if investigations %}
      {% for item in investigations %}
      **{{ item.title }}** ({{ item.severity | upper }}) — `{{ item.status }}`

      - Last prompt: {{ as_timestamp(item.last_generated_at) | timestamp_custom('%Y-%m-%d %H:%M', true) if item.last_generated_at else 'Unknown' }}
      - Prompt generations: {{ item.generation_count }}
      - File: `{{ item.prompt_path }}`

      {% endfor %}
      {% else %}
      No focused investigations have been generated yet.
      {% endif %}
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
        name: Unknown (raw)
      - entity: sensor.actionable_unknown_entities
        name: Actionable unknown
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


The `Unknown Entities` sensor is the raw count and includes all unknown states. The `Actionable Unknown Entities` sensor excludes `button` entities because buttons are stateless actions and an unknown state is expected. Overall health status, active issues, recommendations, and integration attention use actionable unknown counts; raw counts remain visible for transparency. Other unknown entity domains remain actionable and should be reviewed in context.

The `Integration Attention Domains` sensor counts provider integrations with setup errors/retries, unavailable registered entities, or actionable unknown registered entities. Its attributes on the sensor and Health Status entity show a bounded, severity-ranked domain list. Raw unknown counts are retained separately. This is a triage correlation, not proof of a shared root cause.

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


## Track focused repair investigations

The **Repair Investigations** sensor retains up to 50 focused-prompt records locally. Its attributes show the plan ID, finding title/severity, prompt path, first/last generation times, generation count, and your tracking status. Generating another prompt for the same plan item increments its count rather than creating duplicate history entries.

Use the status service to update your own workflow label:

```yaml
action: home_assistant_health_manager.set_repair_investigation_status
data:
  plan_id: integration_mqtt
  status: in_progress
```

Supported statuses are `prompt_generated`, `in_progress`, `resolved`, `needs_follow_up`, and `dismissed`. Use the exact plan ID from the Repair Investigations sensor attributes. A `resolved` label is only your tracking note; it does not verify that the underlying Home Assistant issue is fixed. Status changes never run repairs or modify integrations, entities, or configuration.


### Update an investigation from the dashboard

The Current diagnostics card includes two additional native dropdowns:

1. **Investigation to Update** — choose an item from the retained investigation history. The option shows its current status, title, and plan ID.
2. **Investigation Status** — choose `prompt_generated`, `in_progress`, `needs_follow_up`, `resolved`, or `dismissed`. The selected investigation is updated immediately and the status dropdown reflects its saved value.

Choose an investigation before changing its status. The selected investigation is an in-memory dashboard selection and resets when Home Assistant restarts; the investigation history and saved statuses remain stored locally. Changing a status only updates your tracking record. A `resolved` label is not a diagnostic verification that the underlying issue has been fixed.


The **Selected Investigation** sensor exposes the chosen history record and, when still present in the latest repair plan, its current finding details: related recommendation IDs, suggested next steps, and structured evidence. The selection is session-only. If a finding is no longer in the latest repair plan, its retained history and prompt path remain visible and the detail card explains that current plan details are unavailable. This view is diagnostic context only; suggested actions are not executed.


## Entity classification review

The Health Manager stores classifications separately from diagnostic history. Raw unknown and unavailable totals remain unchanged; only explicitly classified `expected`, `setup_in_progress`, or `seasonal` entities are excluded from actionable counts. `actionable` classifications remain actionable. Unclassified entities remain subject to the normal domain-based rules.

Use the **Entity Classification to Review** selector to inspect a saved record. Its attributes show the entity ID, classification, reason, source integration, observed availability, and why review was triggered. Select **Confirm selected classification review** only after checking the record; this updates its review timestamp and clears the current review flag without changing the classification or reason. For bulk confirmation, call `home_assistant_health_manager.review_entity_classifications` with `entity_ids` containing the exact entity IDs you reviewed.

To change a classification, call `home_assistant_health_manager.set_entity_classification` with the entity ID, new classification, and a meaningful reason. To remove only the saved classification, call `home_assistant_health_manager.remove_entity_classification`. Neither service changes or deletes the Home Assistant entity. A classification is never changed automatically.

Scheduled review cadence is configured by `home_assistant_health_manager.set_classification_review_interval` (`30`, `60`, `90`, or `manual`). Manual disables calendar-based reviews but event-triggered reviews remain active. Optional persistent notifications are disabled by default; enable **Entity classification review notifications** in the integration options to receive one notification when the set of due entities changes. The notification is updated rather than repeated for an unchanged set and is dismissed when no reviews remain due.
