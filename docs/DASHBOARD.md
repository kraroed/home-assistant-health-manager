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

The card uses only read-only sensors. It does not invoke repair, update, restart, or other control actions.


The `Integration Attention Domains` sensor counts provider integrations with setup errors/retries or unavailable/unknown registered entities. Its attributes on the sensor and Health Status entity show a bounded, severity-ranked domain list. This is a triage correlation, not proof of a shared root cause.

The `Integration Trend Domains` sensor counts provider domains currently in an attention state. Its attributes show report-to-report counts, changes from the previous report, consecutive attention reports, and distinct attention episodes. A domain absent from a later inventory is marked not present rather than assumed resolved. History is local and bounded to 90 generated reports.

Recurring issue sensors count problems that were detected, resolved, and later detected again. The Health Status sensor attributes include the bounded recurrence list with occurrence count and first/last-seen timestamps. Only currently active recurring issues create an additional advisory recommendation; resolved recurring issues remain visible as history. These recommendations never execute repairs.
