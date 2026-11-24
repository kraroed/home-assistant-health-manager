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


## Persistent diagnostic history

The integration stores issue lifecycle records and up to 90 aggregate report-time trend samples using Home Assistant's local Store helper. Issue occurrence counts increase only when an issue previously marked resolved becomes active again; repeated observations during the same active period update last-seen metadata without incrementing recurrence. Recurrence summaries expose rule identifiers, short titles, severity, status, occurrence counts, and timestamps. Active recurring issues produce an additional advisory recommendation. This is recurrence of a diagnostic rule, not proof of an identical root cause. Trend samples store aggregate counts and statuses only. Neither history stores entity IDs, config-entry IDs, raw log text, or configuration contents.

## Persisted-state recovery

The coordinator validates the shape of its local schedule store during setup before registering its periodic callback. If the top-level stored value is not a dictionary, it starts from safe defaults. Invalid history containers and malformed history records are discarded individually, while valid records and unknown forward-compatible keys are preserved. Invalid cached repair-plan/compatibility objects and invalid report counters are reset to safe defaults. This is a recovery boundary for malformed local state, not a backup or migration mechanism; users should still keep normal Home Assistant backups.


## Report publication recovery

Report JSON, text, prompt, and ZIP artifacts are assembled in a temporary directory before publication. A hidden pending marker is created before the staged files are moved into the reports directory. The coordinator records the published ZIP path in the local Store and only then finalizes the marker. On startup, pending transactions are reconciled against that persisted path: a transaction referenced by the Store is finalized, while an unreferenced transaction and its partial artifacts are removed. Abandoned staging directories are also removed. Existing reports without transaction markers are left untouched. This closes the restart window between report publication and Store persistence; it does not replace normal backups.

Focused repair prompts use the same recoverable publication pattern: a pending marker is created before the prompt file is written, the investigation record (including the prompt path) is saved to the local Store, and the marker is removed only after that save succeeds. On startup, a pending prompt whose path is present in persisted investigation history is preserved; an uncommitted prompt is removed. This prevents abandoned focused-prompt files after a crash or failed Store write.

Scheduled report generation now advances its weekly or monthly due date in the same candidate schedule and Store write that commits the report metadata. A restart after a successful report commit therefore does not cause the same overdue scheduled review to be generated again simply because a separate due-date save was interrupted.

Cancellation handling: report and focused-prompt writers run in worker threads, which cannot be stopped by cancelling the awaiting coroutine. The async wrappers therefore shield the worker, wait for it to finish after cancellation, and remove the uncommitted artifacts and pending marker before propagating cancellation. If cancellation occurs later during the Store save, the pending marker remains as a recovery signal for the next startup.


## Entity classification disappearance grace period

A classified entity that is absent is retained with its first missing timestamp. The default 20-minute configurable grace period avoids treating brief Home Assistant restart/reload gaps as actionable review events. If the entity returns within the grace period, the recovery timestamp and duration are retained without raising a review flag. If it remains absent beyond the grace period, or returns at or after that period, the classification is flagged for user review. Recovery status, timestamp, and duration are scoped to the latest disappearance episode and are cleared when a new episode starts. A return at or after the threshold is labeled after-grace; an invalid duration is explicitly labeled unknown. Legacy transient flags are reconciled only when their review timestamp matches the same short-return event, so a later brief restart cannot erase a review earned by an earlier prolonged outage. Source identity and availability-change triggers remain independent and are never cleared by transient-disappearance reconciliation. Existing classifications and their user-authored reasons are never changed by this logic.
