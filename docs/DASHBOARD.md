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
      **Unavailable (actionable / raw):** {{ states('sensor.actionable_unavailable_entities') }} / {{ states('sensor.unavailable_entities') }}
      **Persistent unavailable:** {{ states('sensor.persistent_unavailable_entities') }} / {{ states('sensor.tracked_unavailable_entities') }} tracked
      **Missing tracked entities:** {{ states('sensor.missing_tracked_entities') }}
      **Unavailable investigation groups:** {{ states('sensor.unavailable_investigation_group_count') }}
      **Unknown (actionable / raw):** {{ states('sensor.actionable_unknown_entities') }} / {{ states('sensor.unknown_entities') }}
      **Classification reviews due:** {{ states('sensor.classification_reviews_due') }}
      **Last assessment:** {{ state_attr('sensor.health_overview', 'last_assessment') or 'Not yet assessed' }}
      **Last report:** {{ state_attr('sensor.health_overview', 'last_report') or 'No report yet' }}
      **Failed integrations:** {{ states('sensor.failed_integrations') }}

      **Platform updates:** Core {{ states('sensor.core_update') | replace('_', ' ') }}, Supervisor {{ states('sensor.supervisor_update') | replace('_', ' ') }}, OS {{ states('sensor.operating_system_update') | replace('_', ' ') }}

      **Diagnostic trend:** {{ states('sensor.diagnostic_trend') | replace('_', ' ') | title }}
      **Diagnostic coverage:** {{ states('sensor.diagnostic_coverage') }}%
      **Compatibility:** {{ states('sensor.compatibility_status') | replace('_', ' ') | title }}

      {% set groups = state_attr('sensor.health_overview', 'unavailable_investigation_groups') or [] %}
      **Unavailable entity groups needing review**
      {% for group in groups[:8] %}
      - **{{ group.title }}** ({{ group.confidence }}) — {{ group.entity_ids | join(', ') }}
        - Evidence: {{ group.evidence | join('; ') }}
      {% else %}
      - No unavailable entity groups currently meet the grouping criteria
      {% endfor %}

      {% set attention = state_attr('sensor.health_status', 'integration_attention_domains') or [] %}
      **Integration attention areas**
      {% for item in attention[:5] %}
      - **{{ item.domain }}** ({{ item.severity | upper }}) — {{ item.unavailable_entity_count }} unavailable, {{ item.actionable_unknown_entity_count }} actionable unknown
      {% else %}
      - No integration attention areas were reported
      {% endfor %}

      _Raw unknown counts include stateless buttons. Actionable unknown counts exclude buttons. Coverage describes collected diagnostic sources; it is not a health score._
  - type: entities
    title: Health metrics — live values
    show_header_toggle: false
    entities:
      - entity: sensor.health_overview
        name: Overall health and consolidated details
      - entity: sensor.active_issues
        name: Active issues
      - entity: sensor.unavailable_entities
        name: Unavailable (raw)
      - entity: sensor.tracked_unavailable_entities
        name: Tracked unavailable
      - entity: sensor.persistent_unavailable_entities
        name: Persistent unavailable
      - entity: sensor.missing_tracked_entities
        name: Missing tracked entities
      - entity: sensor.unavailable_investigation_group_count
        name: Unavailable investigation groups
      - entity: sensor.unavailable_investigation_count
        name: Saved unavailable investigations
      - entity: sensor.unavailable_investigations_needing_review
        name: Unavailable investigations needing review
      - entity: sensor.selected_unavailable_investigation
        name: Selected unavailable investigation
      - entity: select.home_assistant_health_manager_unavailable_group_to_investigate
        name: Persistent unavailable group to investigate
      - entity: button.home_assistant_health_manager_start_unavailable_investigation
        name: Start selected group investigation
      - entity: text.home_assistant_health_manager_unavailable_entity_to_investigate
        name: Entity ID for immediate manual investigation
      - entity: button.home_assistant_health_manager_start_manual_unavailable_investigation
        name: Start immediate manual investigation
      - entity: select.home_assistant_health_manager_unavailable_investigation_to_update
        name: Unavailable investigation to update
      - entity: select.home_assistant_health_manager_unavailable_investigation_status
        name: Unavailable investigation status
      - entity: text.home_assistant_health_manager_unavailable_investigation_note
        name: Unavailable investigation note
      - entity: sensor.actionable_unavailable_entities
        name: Unavailable (actionable)
      - entity: sensor.unknown_entities
        name: Unknown (raw)
      - entity: sensor.actionable_unknown_entities
        name: Unknown (actionable)
      - entity: sensor.failed_integrations
        name: Failed integrations
      - entity: sensor.classification_reviews_due
        name: Classifications needing review
      - entity: sensor.diagnostic_coverage
        name: Diagnostic coverage
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
      - entity: select.home_assistant_health_manager_entity_classification_value
        name: Classification value to apply
      - entity: text.home_assistant_health_manager_entity_classification_target
        name: Entity ID to classify or edit
      - entity: text.home_assistant_health_manager_entity_classification_reason
        name: Explanation for classification
      - entity: button.home_assistant_health_manager_apply_entity_classification
        name: Apply selected classification
      - entity: button.home_assistant_health_manager_remove_entity_classification
        name: Remove selected classification
      - entity: select.home_assistant_health_manager_classification_review_interval
        name: Classification review interval
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

The **Health Overview** sensor is a consolidated, read-only summary. Its state mirrors the overall health status (`healthy` or `attention`), and its attributes contain the current issue counts, raw and actionable unknown/unavailable counts, integration status, platform update states, classification review queue, diagnostic coverage, compatibility, trends, and report metadata. Use the individual sensors for history graphs and focused inspection; the overview sensor is intended for one-place dashboards and automations.


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

To create or change a classification in the dashboard, enter an existing entity ID in **Entity ID to Classify** (or choose an existing saved record in **Entity Classification to Review**), choose the value in **Classification Value**, enter a meaningful explanation in **Entity Classification Reason**, then press **Apply Entity Classification**. The reason is required. To remove only the saved classification, select the entity and press **Remove Entity Classification**. This removes only the saved metadata; it does not delete or alter the Home Assistant entity. The equivalent explicit services remain available: `home_assistant_health_manager.set_entity_classification` and `home_assistant_health_manager.remove_entity_classification`. A classification is never changed automatically.

Scheduled review cadence is configured with the **Classification Review Interval** selector (`30`, `60`, `90`, or `manual`); the equivalent service is `home_assistant_health_manager.set_classification_review_interval`. Manual disables calendar-based reviews but event-triggered reviews remain active. Optional persistent notifications are disabled by default; enable **Entity classification review notifications** in the integration options to receive one notification when the set of due entities changes. The notification is updated rather than repeated for an unchanged set and is dismissed when no reviews remain due.


## Unavailable entity observation and grouping

The integration keeps a separate local observation store for entities that become unavailable. The default persistence threshold is 60 minutes and can be adjusted in the integration options (5 minutes to 24 hours). Shorter outages remain visible in the raw unavailable count but do not enter the persistent-unavailable count until the threshold is reached.

An entity that disappears from the state registry is recorded as missing, not recovered. Its original unavailable timestamp is retained. Recovery is recorded only when the entity is seen again in a non-unavailable state.

The overview lists groups only after the configured persistence threshold has been reached, and only when there is supporting association evidence: multiple entities on the same registered device, multiple entities from an integration with a setup error/retry, or multiple entities from one integration whose unavailable transitions began within five minutes. Same-integration entities with no such evidence remain separate. Grouping can be disabled in the options. A group is an investigation lead, not a confirmed root cause; every group remains subject to user review and no entity is automatically classified or suppressed.


## Managing unavailable-entity investigations

Use **Start Unavailable Entity Investigation** to begin tracking a persistent group. This records your decision locally; it does not alter Home Assistant entities or their classifications. For a transient outage that needs immediate attention, the `home_assistant_health_manager.start_unavailable_investigation` service accepts an explicit list of currently unavailable entity IDs and bypasses the persistence threshold.

Use **Unavailable Investigation to Update** to inspect saved records, then **Unavailable Investigation Status** to choose `needs_review`, `investigating`, `waiting`, `resolved`, or `expected`. The `waiting` status schedules a reminder using the configured interval. An `expected` status is only a user tracking decision; it does not suppress the entity from health counts or create an entity classification. The Health Overview exposes the saved records, status counts, evidence, and reminder timestamps.

## Unavailable entity investigations

Automatic unavailable-entity groups appear only after the configured persistence threshold. Select a group in **Persistent Unavailable Group to Investigate**, then press **Start Selected Group Investigation**. For an outage that needs attention before the threshold, enter one currently unavailable entity ID in **Entity ID for Immediate Manual Investigation** and press **Start Immediate Manual Investigation**. The equivalent service supports multiple entity IDs:

```yaml
action: home_assistant_health_manager.start_unavailable_investigation
data:
  entity_ids:
    - sensor.example
```

Choose a saved record in **Unavailable Investigation to Update**, enter an optional note, then choose a status:

- `needs_review` — awaiting your review
- `investigating` — you are actively investigating it
- `waiting` — defer it; a reminder is scheduled using the configured interval
- `resolved` — your tracking decision that the issue is resolved
- `expected` — your decision that this outage is expected in its current context

`Resolved` and `Expected` are not technical verification, entity classifications, or suppression rules. Raw and actionable unavailable counts continue to include those entities. A changed group membership, changed evidence, or a new outage cycle can prompt another review. Investigation history is retained separately from entity classifications and diagnostic report history.

Persistent notifications can be enabled in the integration options. They update when the due group set or its evidence changes, and reminders follow the configured interval. The notification does not attempt repairs.
