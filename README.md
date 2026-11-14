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

## AI repair and validation prompt\nEvery generated report includes a standalone `*_ai_repair_prompt.md` file, also bundled in the report ZIP. The `generate_ai_repair_prompt` service creates a fresh report and fires the `home_assistant_health_manager_ai_repair_prompt_created` event with the report and prompt file paths. The prompt is copy-ready for an AI assistant or agent and includes a bounded, redacted diagnostic summary, platform versions/update state, and the integration's findings. It asks the AI to verify the live installation, research current official documentation and release notes, cite version-specific sources, explain risks and rollback, guide one repair at a time, and validate each approved change. It explicitly forbids changes without the user's separate approval.\n\nThe latest compatibility triage is also exposed through the `Compatibility Status` sensor and the Health Status sensor attributes. Possible results distinguish existing issues, platform updates requiring review, missing platform data, and no platform update reported. It is deliberately a limited local assessment, not a compatibility guarantee.\n\nThe prompt is generated locally. It excludes raw log lines, entity IDs, and configuration contents; however, redaction is best-effort, so users should review it before sharing. The integration does not send the prompt to an AI service. The user chooses where and with whom to share it.\n\n## Current collection scope\n- Home Assistant Core version.
- Installed/latest versions and update state for Home Assistant Core, Supervisor, and Home Assistant OS when their official Supervisor update entities are available.
- Release summary and release-note URL supplied by those official update entities.
- Entity totals and counts by domain/state, with dedicated unavailable and unknown entity sensors and per-domain breakdowns.
- Config-entry totals by integration domain and setup state, plus failed integration domains (without collecting entry data/options).
- Bounded tail of the default Core log, if readable.
- Error/warning counts and repeated log-message patterns.
- Persistent issue lifecycle history: first/last detection, recurrence count, current/resolved status, and aggregate counts.
- Conservative rule-based recommendations with evidence and suggested next steps.
- Compatibility triage that combines Core/Supervisor/OS update status with existing failed integrations and Core log errors, without claiming that all custom integrations or add-ons are compatible.

Platform update awareness reads Home Assistant's existing `update` entities. It does not call private Supervisor endpoints, use a Supervisor token, fetch release metadata independently, install updates, or restart the host. If the Supervisor integration or one of its update entities is unavailable, the corresponding status is reported as missing/unknown rather than guessed.\n\nUpdate recommendations include installed/latest versions and any release information exposed by Home Assistant. Before applying an update, review the linked official release notes and current upgrade guidance, check custom integration/app compatibility, verify a full backup, and choose a maintenance window. Recommendations are informational and never execute an update.\n\nMonthly reports include the current inventory, setup-state breakdowns, platform update versions, and accumulated issue history. They are not yet historical entity trend analyses or full Supervisor/host/recorder/automation audits; those remain future work.

The integration does not collect unrestricted YAML, secrets files, entity attributes, recorder databases, or original unredacted logs. Issue history stores only rule identifiers, short titles, severity, timestamps, and occurrence counts; it does not store entity IDs or raw log lines.

## Privacy warning
Redaction is best-effort pattern matching for common secrets and identifiers, including email, IP/MAC addresses, UUIDs, entity IDs, location-like coordinates, and common home-directory paths. It is not a guarantee that every identifier or secret is removed. Review an export before sharing it. The original Core log is read in memory and only the sanitized version is written to a report.

## Validation
GitHub Actions runs Home Assistant hassfest and HACS integration validation on pushes and pull requests.

## Status
Early development build. Supervisor/OS logs, host metrics, recorder internals, automation traces, dashboard resources, and approved remediation execution are future work. This release is read-only and is not a complete security audit.
