# Home Assistant Health Manager

A local-first Home Assistant custom integration for scheduled health diagnostics, privacy-aware report generation, and human-approved remediation planning.

## Design commitments

- **Local only:** no telemetry, cloud processing, remote uploads, or outbound network requests.
- **Read-only diagnostics:** no configuration changes, restarts, entity deletion, or device control.
- **Approval required:** this release recommends actions only. It never applies fixes.
- **Scheduled reviews:** weekly diagnostic reports and monthly comprehensive reports.
- **Sanitized exports:** reports are written locally under `/config/health_manager/reports`.
- **Retention:** report files older than the configured retention period are removed locally.

## Development installation

Copy `custom_components/home_assistant_health_manager` into your Home Assistant `custom_components` directory, restart Home Assistant, then add **Home Assistant Health Manager** under Settings → Devices & services.

## Services

- `home_assistant_health_manager.run_diagnostics`
- `home_assistant_health_manager.generate_report`
- `home_assistant_health_manager.generate_ai_repair_prompt`
- `home_assistant_health_manager.generate_focused_repair_prompt` (requires the exact `plan_id` from the latest repair-plan sensor attributes)
- `home_assistant_health_manager.set_repair_investigation_status` (updates a user-maintained tracking label only)

## AI repair and validation prompt

Every generated report includes a standalone `*_ai_repair_prompt.md` file, also bundled in the report ZIP. The `generate_ai_repair_prompt` service creates a fresh report and fires the `home_assistant_health_manager_ai_repair_prompt_created` event with the report and prompt file paths. The prompt is copy-ready for an AI assistant or agent and includes a bounded, redacted diagnostic summary, platform versions/update state, configured integration-domain inventory, and the integration's findings. It asks the AI to verify the live installation, research current official documentation and release notes, cite version-specific sources, explain risks and rollback, guide one repair at a time, and validate each approved change. It explicitly forbids changes without the user's separate approval.

The latest compatibility triage is exposed through the `Compatibility Status` sensor and the Health Status sensor attributes. It combines platform update status, existing failures, Core log errors, and integration inventory counts. It is deliberately a limited local assessment, not a compatibility guarantee.

The prompt is generated locally. It excludes raw log lines, entity IDs, config-entry IDs, titles, and configuration contents; however, redaction is best-effort, so users should review it before sharing. The integration does not send the prompt to an AI service. The user chooses where and with whom to share it.

## Current collection scope

- Home Assistant Core version.
- Installed/latest versions and update state for Home Assistant Core, Supervisor, and Home Assistant OS when their official update entities are available.
- A bounded inventory of all available update entities, including the registry-backed provider integration domain, associated config-entry domain when resolvable, state, exposed versions, release summary, and release URL. Provider domain is explicitly not treated as proof of the package being updated.
- Release summary and release-note URL supplied by those update entities.
- Entity totals and counts by domain/state, with dedicated unavailable and unknown entity sensors and per-domain breakdowns.
- Config-entry totals by integration domain and setup state, plus registered entity totals and unavailable/unknown counts grouped by the providing integration domain. A bounded attention list prioritizes setup errors, setup retries, and affected entity counts.
- Failed config-entry domains, without collecting entry data/options.
- Bounded tail of the default Core log, if readable.
- Error/warning counts and repeated log-message patterns.
- Conservative Core log attribution for entries whose logger explicitly begins with `homeassistant.components.<domain>` or `custom_components.<domain>`. Counts are grouped by the logger's domain and severity; generic loggers, free-text mentions, and other namespaces remain unattributed. This identifies the emitting logger namespace, not necessarily the root cause. No raw message text is added to the structured attribution summary.
- Persistent issue lifecycle history: first/last detection, recurrence count, current/resolved status, and aggregate counts.
- Bounded diagnostic change history: configured integration domains, aggregate setup-state changes, platform update signals, update-entity inventory changes, and total/unavailable/unknown entity counts with total, unavailable, and unknown breakdowns by domain across snapshots. This helps surface changes in entity inventory by domain without retaining individual entity identifiers. It stores aggregate counts, not entity IDs.
- Conservative rule-based recommendations with evidence and suggested next steps.
- Compatibility triage that combines Core/Supervisor/OS update status, existing failed integrations, Core log errors, and inventory coverage without claiming that all custom integrations or add-ons are compatible.

### Integration inventory limits

The integration inventory groups config-entry lifecycle states and registered entity availability counts by the integration platform that provides each entity. Entity IDs are used only for in-memory matching and are not retained. Its bounded attention list ranks domains with setup errors, setup retries, unavailable entities, or unknown entities. The update-entity inventory independently lists update entities and their registry-backed provider integration domains; this identifies which integration supplies the update entity, not necessarily the target component. It intentionally does not collect config-entry IDs, titles, data, options, or credentials. It does not currently determine whether an integration is built into Home Assistant Core, installed through HACS, or manually installed, and it does not infer integration package versions. Update entities may expose versions and release details for other software, but their provider integration must not be confused with the target package. A domain appearing in the inventory is a prompt for further investigation, not proof of source or compatibility. Domain-level entity correlation is based on the entity registry provider platform; it does not prove that all affected entities share one root cause. Core log entries are attributed only when the standard logger field explicitly names `homeassistant.components.<domain>` or `custom_components.<domain>`; generic or ambiguous loggers remain unattributed. This identifies the emitting namespace, not necessarily the root cause. The AI prompt instructs the receiving agent to verify the actual source, installed version, manifest requirements, and current release notes before making compatibility claims.

Platform update awareness reads Home Assistant's existing `update` entities. It does not call private Supervisor endpoints, use a Supervisor token, fetch release metadata independently, install updates, or restart the host. If an update entity is unavailable, the corresponding status is reported as missing/unknown rather than guessed.

Update recommendations include installed/latest versions and any release information exposed by Home Assistant. Before applying an update, review the linked official release notes and current upgrade guidance, check custom integration/add-on compatibility, verify a full backup, and choose a maintenance window. Recommendations are informational and never execute an update.

Monthly reports include the current inventory, setup-state breakdowns, platform update versions, accumulated issue history, and the latest bounded diagnostic change summary. The report-time trend history compares aggregate entity and issue counts, Core log error counts, and diagnostic coverage across generated reports. A separate provider-integration trend history compares each configured provider domain's setup-error/retry counts and registered unavailable/unknown entity counts across reports. It retains up to 90 report samples and tracks distinct attention episodes; continuous attention across adjacent reports is one episode, while a clear period followed by renewed attention counts as recurrence. Domains missing from a later inventory are marked not present, not assumed resolved. The `Integration Trend Domains` sensor counts currently active attention domains and exposes a bounded domain summary with deltas, episode counts, and truncation metadata. This is not a continuous monitor or causal analysis. Full Supervisor/host/recorder/automation audits remain future work.

The integration does not collect unrestricted YAML, secrets files, entity attributes, recorder databases, or original unredacted logs. Issue history stores only rule identifiers, short titles, severity, timestamps, and occurrence counts; it does not store entity IDs or raw log lines.

## Privacy warning

Redaction is best-effort pattern matching for common secrets and identifiers, including email, IP/MAC addresses, UUIDs, entity IDs, location-like coordinates, and common home-directory paths. It is not a guarantee that every identifier or secret is removed. Review an export before sharing it. The original Core log is read in memory and only the sanitized version is written to a report.

## Validation

GitHub Actions runs Python tests, Home Assistant hassfest, and HACS integration validation on pushes and pull requests.

## Status

Early development build. Supervisor/OS logs, host metrics, recorder internals, automation traces, dashboard resources, and approved remediation execution are future work. This release is read-only and is not a complete security audit.


Compatibility triage includes integration domains with setup_error or setup_retry lifecycle states and reports when the bounded update-entity inventory is truncated. These are review signals, not compatibility verdicts.


## Diagnostic collection coverage

Each assessment reports whether entity states, config entries, platform update entities, update entities, integration setup inventory, and the Core log were collected, unavailable, not checked, or disabled. The `Diagnostic Coverage` sensor reports the percentage of assessed sources successfully collected. Sources not checked or disabled are excluded from the percentage and shown separately. Coverage describes data availability only; it is not a health score, compatibility guarantee, or proof that every relevant source was inspected.


## Diagnostic trends

Generated reports retain a bounded history of up to 90 aggregate trend samples. A sample is recorded when a report is generated, not on every coordinator refresh. Trends compare entity totals, unavailable and unknown entity counts, failed config entries, Core log error counts, and diagnostic collection coverage against the previous report sample. The `Diagnostic Trend` sensor reports `insufficient_data`, `improving`, `stable`, `worsening`, or `mixed`; its attributes are available on the Health Status sensor. Entity-total changes are shown but do not by themselves imply improvement or deterioration. Trend direction is a simple comparison, not causal analysis or a health guarantee. The stored history contains aggregate counts and statuses only, without entity IDs, config-entry IDs, log text, or configuration.


## Lovelace dashboard

An optional native Lovelace dashboard example using Markdown, Entities, and History Graph cards is available in [docs/DASHBOARD.md](docs/DASHBOARD.md). It requires no custom frontend resource. Diagnostic sensors are read-only; the focused-prompt selector and investigation-status service are explicit user-triggered local tracking actions.


## Recurring issue detection

Issue history distinguishes repeated observations during one uninterrupted active period from a true recurrence. The occurrence count increases when a previously resolved issue is detected again. Reports and the AI repair prompt include bounded recurrence details, and active recurring issues produce an approval-gated recommendation to investigate the underlying cause rather than repeat a temporary fix. Resolved recurring issues remain visible in history but do not create active recommendations. Recurrence is based on the integration's existing rule identifiers; it does not prove that the same underlying root cause returned. All actions remain user-approved and read-only.


## Prioritized repair plan

Each generated report includes a bounded, severity-sorted repair plan. It groups findings only when they share an exact provider-domain identity (for example, the domain inventory and its trend finding) or an explicit recurring-issue/base-issue identifier. General unavailable-entity, unknown-entity, failed-entry, and log-volume findings remain separate when overlap alone cannot establish a shared cause. Explicit component-logger counts and provider trend deltas/episodes are attached as related evidence, never treated as proof of causation. The JSON report, text summary, and copy-ready AI repair prompt include this plan. Every item remains advisory, requires explicit user approval, and has no automated action available; the plan is capped at 50 items and reports omissions.


The `Prioritized Repair Plan Items` sensor exposes the number of items in the latest generated plan; its attributes provide the bounded plan details, and the Health Status sensor includes the same plan. It updates when a report is generated, not on every coordinator refresh. See [docs/DASHBOARD.md](docs/DASHBOARD.md) for the native Lovelace example.


## Focused repair investigations

After generating a diagnostic report, inspect the `Prioritized Repair Plan Items` sensor attributes and choose one item's exact `plan_id`. Call `home_assistant_health_manager.generate_focused_repair_prompt` with that ID. The service writes a separate Markdown prompt under `/config/health_manager/reports` and fires `home_assistant_health_manager_focused_repair_prompt_created` with the selected ID and prompt path. The focused prompt includes only that plan item, its linked recommendations, and matching provider-domain log/trend evidence where available; unrelated plan items and unrelated provider evidence are excluded. Stale IDs are rejected rather than silently selecting a different item. The prompt is local-only, follows the configured report retention period, and remains approval-gated. Generate a fresh report before selecting an item so the ID and evidence reflect the latest assessment.


## Repair investigation history

The `Repair Investigations` sensor exposes a locally stored, bounded history of up to 50 focused-prompt investigations. It records only the plan ID, finding title/severity, local prompt path, generation timestamps/count, and user-selected status; it does not retain the diagnostic evidence or raw logs in this history. Generating another prompt for the same plan item increments its generation count. The `set_repair_investigation_status` service supports `prompt_generated`, `in_progress`, `resolved`, `needs_follow_up`, and `dismissed`. These are personal workflow labels, not a technical verification of repair. Status updates never execute repairs or change Home Assistant configuration. See [docs/DASHBOARD.md](docs/DASHBOARD.md).


The native dashboard also includes **Investigation to Update** and **Investigation Status** selectors. Choose a retained investigation, then choose its tracking label to update the local history without entering a plan ID or calling a service manually. The selected investigation is a temporary UI selection; its saved history and status persist locally. See [the dashboard guide](docs/DASHBOARD.md).
