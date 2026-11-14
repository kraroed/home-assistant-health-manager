# Home Assistant Health Manager

A local-first Home Assistant custom integration for scheduled health diagnostics, privacy-aware report generation, and human-approved remediation planning.

## Design commitments
- **Local only:** no telemetry, cloud processing, remote uploads, or outbound network requests.
- **Read-only diagnostics:** no configuration changes, restarts, entity deletion, or device control.
- **Approval required:** this release recommends actions only. It never applies fixes.
- **Scheduled reviews:** weekly diagnostic reports and monthly comprehensive reports.
- **Sanitized exports:** reports are written locally under `/config/health_manager/reports`.

## Development installation
Copy `custom_components/home_assistant_health_manager` into your Home Assistant `custom_components` directory, restart Home Assistant, then add **Home Assistant Health Manager** under Settings → Devices & services.

## Services
- `home_assistant_health_manager.run_diagnostics`
- `home_assistant_health_manager.generate_report`

## Current collection scope
- Home Assistant version.
- Entity totals and counts by domain/state.
- Config-entry domain and state summaries (no entry data/options).
- Bounded tail of the default Core log, if readable.
- Error/warning counts and repeated log-message patterns.

The integration does not collect unrestricted YAML, secrets files, entity attributes, recorder databases, or original unredacted logs.

## Privacy warning
Redaction is best-effort pattern matching, not a guarantee that every identifier or secret is removed. Review an export before sharing it. The original Core log is read in memory and only the sanitized version is written to a report.

## Status
Early development build. Supervisor/OS logs, deeper platform diagnostics, issue history, dashboard resources, retention cleanup, and Home Assistant/HACS validation remain future work. Do not treat this release as a complete security audit.
