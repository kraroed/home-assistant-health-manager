# Architecture and privacy boundaries

## Data flow
Home Assistant in-process APIs and the default Core log file → bounded in-memory collection → redaction → sanitized analysis → local JSON/TXT/ZIP output.

## Collection boundaries
The initial collector reads entity states for aggregate counts, config-entry domains and states, the Home Assistant version, and a bounded tail of `home-assistant.log` when readable. It does not read config-entry data/options, entity attributes, secrets files, unrestricted YAML, recorder databases, or original log exports.

Supervisor/OS logs, host metrics, recorder internals, and automation traces are deferred until supported access paths and permissions can be validated.

## Redaction
The initial pattern-based redactor masks common credential assignments, bearer tokens, email addresses, MAC addresses, IPv4 addresses, URL credentials, entity IDs, home-directory usernames, and long token-like strings. Pattern matching cannot guarantee detection of every identifier or secret. Human review is required before sharing.

## Remediation safety
This release is read-only. It does not modify Home Assistant configuration, restart integrations, delete entities, or control devices. Future remediation proposals must include evidence, impact, risk, a rollback plan, and an explicit user approval step before any execution capability is considered.

## Scheduling
A persisted schedule checks for weekly and monthly reports hourly. First-run schedules are set one week and one month after setup rather than creating a large report immediately during installation.
