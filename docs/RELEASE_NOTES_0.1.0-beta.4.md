# Home Assistant Health Manager 0.1.0-beta.4

**Draft release notes — not yet published.** This version follows the published `0.1.0-beta.3` release and is intended to make the new features available for controlled Home Assistant OS beta testing. Live runtime verification is performed after publication, not before it.

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

- Python syntax and unit-test job: passed.
- Home Assistant validation (hassfest): passed.
- HACS validation: passed.
- CI run: https://github.com/kraroed/home-assistant-health-manager/actions/runs/44461418726
- Validated feature-branch commit: `4073068f90838856bae587315ee1bb022d1fb3e1`.
- Re-run all checks on the exact beta.4 release commit before publishing.

## Required before publication

- Complete code review and merge the feature branch into `main`.
- Set the integration manifest version and Git tag to exactly `0.1.0-beta.4`.
- Publish beta.4 as a GitHub pre-release so it can be installed through HACS/Marketplace.
- Re-run all validation against the exact release commit before publishing.
- After publication, install on a backed-up Home Assistant OS instance and complete [the controlled test checklist](HA_OS_TEST_CHECKLIST.md), including classification persistence, event-triggered review, review notifications, dashboard entity IDs, and the consolidated overview.

Live Home Assistant OS verification has not yet been completed for these new features. This draft is not an installable release announcement.
