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
- Config-entry totals by integration domain and setup state, plus a per-domain setup-state inventory.
- Failed config-entry domains, without collecting entry data/options.
- Bounded tail of the default Core log, if readable.
- Error/warning counts and repeated log-message patterns.
- Persistent issue lifecycle history: first/last detection, recurrence count, current/resolved status, and aggregate counts.
- Bounded diagnostic change history: configured integration domains, aggregate setup-state changes, platform update signals, update-entity inventory changes, and total/unavailable/unknown entity counts with total, unavailable, and unknown breakdowns by domain across snapshots. This helps surface changes in entity inventory by domain without retaining individual entity identifiers. It stores aggregate counts, not entity IDs.
- Conservative rule-based recommendations with evidence and suggested next steps.
- Compatibility triage that combines Core/Supervisor/OS update status, existing failed integrations, Core log errors, and inventory coverage without claiming that all custom integrations or add-ons are compatible.

### Integration inventory limits

The integration inventory lists configured domains and their config-entry lifecycle-state counts. The update-entity inventory independently lists update entities and their registry-backed provider integration domains; this identifies which integration supplies the update entity, not necessarily the target component. It intentionally does not collect config-entry IDs, titles, data, options, or credentials. It does not currently determine whether an integration is built into Home Assistant Core, installed through HACS, or manually installed, and it does not infer integration package versions. Update entities may expose versions and release details for other software, but their provider integration must not be confused with the target package. A domain appearing in the inventory is a prompt for further investigation, not proof of source or compatibility. The AI prompt instructs the receiving agent to verify the actual source, installed version, manifest requirements, and current release notes before making compatibility claims.

Platform update awareness reads Home Assistant's existing `update` entities. It does not call private Supervisor endpoints, use a Supervisor token, fetch release metadata independently, install updates, or restart the host. If an update entity is unavailable, the corresponding status is reported as missing/unknown rather than guessed.

Update recommendations include installed/latest versions and any release information exposed by Home Assistant. Before applying an update, review the linked official release notes and current upgrade guidance, check custom integration/add-on compatibility, verify a full backup, and choose a maintenance window. Recommendations are informational and never execute an update.

Monthly reports include the current inventory, setup-state breakdowns, platform update versions, accumulated issue history, and the latest bounded diagnostic change summary. They are not yet historical entity trend analyses or full Supervisor/host/recorder/automation audits; those remain future work.

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
