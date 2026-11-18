# Home Assistant Health Manager 0.1.0-beta.1

**Initial Home Assistant Marketplace testing beta — pre-release (HACS-compatible repository).**

This beta is intended to let the maintainer install the integration through HACS and begin controlled Home Assistant OS testing. It is not a stable release and has not yet completed live HA OS runtime validation.

## Included

- Local-only diagnostic collection and health reports.
- Entity availability and config-entry inventory.
- Home Assistant Core, Supervisor, and OS update-entity awareness.
- Diagnostic coverage, issue history, trends, and compatibility triage.
- Sanitized report exports with a prominent manual-review warning.
- Approval-gated full and focused AI investigation prompts.
- Local repair-investigation tracking.
- Bounded report retention and startup recovery for interrupted report publication.
- Native Lovelace dashboard example.

## Safety and privacy

- No telemetry, cloud processing, remote uploads, or outbound network requests are part of the integration's diagnostic workflow.
- Diagnostics are read-only. The integration does not apply repairs, install updates, restart Home Assistant, or change device configuration.
- Redaction is best-effort, not a guarantee. Review every export before sharing it.
- This is not a complete security audit or compatibility guarantee.

## Known validation limitation

Repository unit tests, Home Assistant hassfest, and HACS validation pass on the tagged commit. Live HA OS installation, report inspection, restart/persistence, retention, and disposable-instance fault-injection tests remain to be completed using [the test checklist](HA_OS_TEST_CHECKLIST.md).

## Testing

Add this repository from Settings → Marketplace → Add from link, enable its Pre-release switch, and install `0.1.0-beta.1`. Then follow the controlled HA OS checklist. Take and verify a full backup before installing on a system containing important data. Run destructive fault-injection tests only in a disposable HA OS instance.
