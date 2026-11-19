# Home Assistant Health Manager 0.1.0-beta.4

**Draft release notes — not yet published.** This version is intended to follow the published `0.1.0-beta.3` release after the feature branch is merged and controlled Home Assistant OS verification is completed.

## What's new

- Persistent, user-managed entity classifications: `actionable`, `expected`, `setup_in_progress`, and `seasonal`.
- Classification reasons are required and retained separately from diagnostic reports.
- Raw unknown and unavailable inventory counts remain unchanged; explicitly non-actionable classifications affect only actionable counts.
- Classification review scheduling supports manual, 30-, 60-, and 90-day intervals.
- Entities are flagged for review after qualifying disappearance/return, source identity, or availability changes; classifications are never changed automatically.
- Native Home Assistant controls to select or enter an entity ID, choose a classification, provide a reason, apply or remove the saved classification, and confirm reviews.
- Optional deduplicated persistent review notifications, disabled by default.
- New consolidated `sensor.health_overview` with current health state and diagnostic attributes.
- Updated native Lovelace dashboard with actionable/raw counts, review queue, assessment/report timestamps, and individual diagnostic entities.

## Compatibility and data handling

- Existing individual diagnostic sensors remain available.
- Classification metadata is stored separately and persists across restarts.
- Removing a classification removes only its metadata; it does not delete or change the Home Assistant entity.
- Confirming a review changes review metadata only, not the classification or reason.
- Existing classifications are never automatically reclassified.

## Automated validation

- Python syntax and unit tests: 161 passed on the feature branch.
- Home Assistant validation: passed.
- HACS validation: passed.
- CI run: https://github.com/kraroed/home-assistant-health-manager/actions/runs/44460272996
- Validated feature-branch commit: `a4db9ec6d79b53ade9ede2fd9ba704d726647519`.

## Required before publication

- Merge the reviewed feature branch into `main`.
- Complete a backed-up installation and live verification on Home Assistant OS using [the controlled test checklist](HA_OS_TEST_CHECKLIST.md).
- Verify classification persistence, event-triggered review, review notifications, dashboard entity IDs, and the consolidated overview against the live installation.
- Re-run all validation against the exact release commit.

Live Home Assistant OS verification has not yet been completed for these new features. This draft is not an installable release announcement.