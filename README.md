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

## Current collection scope
- Home Assistant version.
- Entity totals and counts by domain/state, with dedicated unavailable and unknown entity sensors and per-domain breakdowns.
- Config-entry totals by integration domain and setup state, plus failed integration domains (without collecting entry data/options).
- Bounded tail of the default Core log, if readable.
- Error/warning counts and repeated log-message patterns.
- Persistent issue lifecycle history: first/last detection, recurrence count, current/resolved status, and aggregate counts.
- Conservative rule-based recommendations with evidence and suggested next steps.

Monthly reports include the current inventory, setup-state breakdowns, and accumulated issue history. They are not yet historical entity trend analyses or full Supervisor/host/recorder/automation audits; those remain future work.

The integration does not collect unrestricted YAML, secrets files, entity attributes, recorder databases, or original unredacted logs. Issue history stores only rule identifiers, short titles, severity, timestamps, and occurrence counts; it does not store entity IDs or raw log lines.

## Privacy warning
Redaction is best-effort pattern matching for common secrets and identifiers, including email, IP/MAC addresses, UUIDs, entity IDs, location-like coordinates, and common home-directory paths. It is not a guarantee that every identifier or secret is removed. Review an export before sharing it. The original Core log is read in memory and only the sanitized version is written to a report.

## Validation
GitHub Actions runs Home Assistant hassfest and HACS integration validation on pushes and pull requests.

## Status
Early development build. Supervisor/OS logs, host metrics, recorder internals, automation traces, dashboard resources, and approved remediation execution are future work. This release is read-only and is not a complete security audit.
