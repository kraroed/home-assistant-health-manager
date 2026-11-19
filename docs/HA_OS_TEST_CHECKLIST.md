# Controlled Home Assistant OS installation test

This checklist validates Home Assistant Health Manager on a running Home Assistant OS installation. Automated CI checks are not a substitute for a live runtime test.

> **Runtime status:** The integration has passed the repository's Python syntax/unit tests, Home Assistant hassfest validation, and HACS validation in GitHub Actions. These checks do not establish that the integration has been tested on a live Home Assistant OS instance. Record the tested commit and actual HA OS results before declaring runtime validation complete.

## Safety boundaries

- Normal installation, configuration, diagnostics, report inspection, prompt generation, dashboard setup, and ordinary restart checks can be performed on a backed-up Home Assistant installation.
- Do not perform destructive tests, forced process termination, filesystem fault injection, manual transaction-marker manipulation, or simulated power loss on a production instance.
- Perform fault injection and forced retention-expiry tests only in a disposable HA OS test instance or isolated test environment.
- This integration is read-only. It creates local reports and tracking records; it does not apply repairs, update Home Assistant, restart services, or modify device configuration.
- Review every report before sharing. Redaction is best-effort and is not a guarantee that all secrets or identifying information have been removed.

## Repository and CI evidence

- Repository: https://github.com/kraroed/home-assistant-health-manager
- README: https://github.com/kraroed/home-assistant-health-manager/blob/main/README.md
- Manifest: https://github.com/kraroed/home-assistant-health-manager/blob/main/custom_components/home_assistant_health_manager/manifest.json
- Config/options flow: https://github.com/kraroed/home-assistant-health-manager/blob/main/custom_components/home_assistant_health_manager/config_flow.py
- Integration setup/unload: https://github.com/kraroed/home-assistant-health-manager/blob/main/custom_components/home_assistant_health_manager/__init__.py
- Coordinator and schedule: https://github.com/kraroed/home-assistant-health-manager/blob/main/custom_components/home_assistant_health_manager/coordinator.py
- Sensors: https://github.com/kraroed/home-assistant-health-manager/blob/main/custom_components/home_assistant_health_manager/sensor.py
- Select entities: https://github.com/kraroed/home-assistant-health-manager/blob/main/custom_components/home_assistant_health_manager/select.py
- Service schemas: https://github.com/kraroed/home-assistant-health-manager/blob/main/custom_components/home_assistant_health_manager/services.yaml
- Report implementation: https://github.com/kraroed/home-assistant-health-manager/blob/main/custom_components/home_assistant_health_manager/report.py
- Dashboard: https://github.com/kraroed/home-assistant-health-manager/blob/main/docs/DASHBOARD.md
- Report transaction tests: https://github.com/kraroed/home-assistant-health-manager/blob/main/tests/test_report_transactions.py
- Latest inspected CI run: https://github.com/kraroed/home-assistant-health-manager/actions/runs/43730001710

Record the exact commit tested. Recheck the Actions page if testing a later revision; do not assume the linked run validates a different commit.

## 1. Pre-install backup and prerequisites

**Test type:** Safe on production, provided a recovery backup is available.

- [ ] Home Assistant OS is healthy and startup has completed.
- [ ] Create a full Home Assistant backup.
- [ ] Wait for backup completion and download a copy outside Home Assistant.
- [ ] Record Core, Supervisor, and OS versions.
- [ ] Confirm access to Home Assistant logs and the `/config` directory.
- [ ] Record the repository commit and integration version that will be installed.

**Expected:** A completed, downloadable backup exists and the pre-install environment is recorded.

Stop if backup creation fails or you cannot restore the system.

## 2. Install from the Home Assistant Marketplace and restart

**Test type:** Safe on production with the backup above.

The current Home Assistant interface uses **Settings → Marketplace** (the successor to the older HACS interface).

Repository URL:

`https://github.com/kraroed/home-assistant-health-manager`

1. Open **Settings → Marketplace**.
2. If prompted, connect your GitHub account. The Marketplace needs this connection to add and update custom repositories.
3. In the upper-right corner, select **Add from link**.
4. Enter the repository URL above under **GitHub link**, then select **Add**. If the Marketplace cannot identify the content type automatically, choose **Integration**.
5. Open the Home Assistant Health Manager repository page.
6. Enable the repository's **Pre-release** switch. This is required to receive `0.1.0-beta.1`; pre-releases are not offered by default.
7. Select **Install**, verify the version shown is `0.1.0-beta.1`, and confirm.
8. Follow the Marketplace prompt if a restart is required. Otherwise, restart Home Assistant normally before adding the integration.
9. Wait for startup to finish.

- [ ] Marketplace accepts the custom repository.
- [ ] Repository is identified as an integration.
- [ ] Pre-release switch is enabled.
- [ ] Install dialog offers `0.1.0-beta.1`.
- [ ] Integration installation completes.
- [ ] Home Assistant starts normally.
- [ ] No new import/setup errors for `home_assistant_health_manager` appear.
- [ ] Marketplace shows the integration as installed.

**Expected:** The beta can be installed through the current Marketplace UI and imported without startup errors.

If the pre-release version does not appear immediately after publishing, refresh the repository information or allow time for Marketplace's release metadata to update. Do not install the default-branch commit as a substitute for verifying the tagged beta.

## 3. Add the integration and review options

**Test type:** Safe on production.

1. Open **Settings → Devices & services → Add integration**.
2. Search for **Home Assistant Health Manager**.
3. Complete the setup form; the current flow asks for an integration name.
4. Open its options and inspect the settings.

Current options and defaults:

| Option | Default |
|---|---:|
| Weekly reports | Enabled |
| Monthly comprehensive reviews | Enabled |
| Include sanitized Core log | Enabled |
| Entity classification review notifications | Disabled |
| Report retention | 90 days |

Retention is constrained to 7–365 days.

- [ ] One config entry is created.
- [ ] A second instance is rejected as unsupported.
- [ ] Options are displayed with expected defaults.
- [ ] Options save and the integration reloads successfully.
- [ ] No setup errors appear in the logs.

**Expected:** One functioning integration entry with configurable report scheduling, Core log collection, and retention.

The coordinator checks scheduled work hourly. The initial schedule is approximately seven days to the first weekly report and 30 days to the first monthly report. Do not expect an automatic report immediately after installation.

## 4. First diagnostic and entity verification

**Test type:** Safe on production.

Open **Developer Tools → Actions** and run:

```yaml
action: home_assistant_health_manager.generate_report
data:
  comprehensive: false
```

The other diagnostic entry point is `home_assistant_health_manager.run_diagnostics`. The service definitions are in `services.yaml`.

Search Developer Tools → States for entities belonging to the integration. The current code defines 31 sensors, 7 select entities, 2 text entities, and 2 button entities. Verify the actual entities created by Home Assistant rather than assuming IDs. Entity IDs may be prefixed differently by Home Assistant; verify actual IDs rather than assuming dashboard examples are exact.

Sensor names to look for include:

- Health Status; Active Issues
- Unavailable Entities; Unknown Entities
- Failed Integrations; Configured Integrations
- Integration Attention Domains; Integration Trend Domains
- Tracked Issues; Active Tracked Issues; Resolved Tracked Issues
- Recurring Issues; Active Recurring Issues
- Prioritized Repair Plan Items; Repair Investigations; Selected Investigation
- Core Update; Supervisor Update; Operating System Update
- Compatibility Status; Diagnostic Change Events; Diagnostic Coverage
- Diagnostic Trend; Generated Reports

Select entities:

- Generate Focused Repair Prompt
- Investigation to Update
- Investigation Status

- [ ] Expected sensor entities are created.
- [ ] All seven select entities are created.
- [ ] Both classification text entities are created.
- [ ] Both classification action buttons are created.
- [ ] `sensor.health_overview` is created and mirrors the current overall health state.
- [ ] Numeric sensors expose sensible numeric values.
- [ ] Text sensors expose understandable states.
- [ ] Relevant attributes are present.
- [ ] The report-generation action succeeds.
- [ ] Generated Reports increases and Health Status refreshes.
- [ ] Diagnostic coverage is populated.
- [ ] No new integration errors appear.

**Expected:** A first weekly diagnostic report is generated. Some states such as `not_detected` or `insufficient_data` are legitimate when the relevant platform entity or historical sample is not available.

## 5. Inspect report artifacts

**Test type:** Safe on production.

Reports are written under:

`/config/health_manager/reports`

For a generated report, inspect:

- `health_report_*.json`
- `health_report_*.txt`
- `health_report_*_ai_repair_prompt.md`
- `health_report_*.zip`

The ZIP is expected to contain `health_report.json`, `summary.txt`, `ai_repair_prompt.md`, and a sanitized Core log when one was collected.

- [ ] JSON exists and parses.
- [ ] TXT summary is readable.
- [ ] AI prompt Markdown exists and is readable.
- [ ] ZIP opens successfully.
- [ ] ZIP contains the expected files.
- [ ] Timestamps, report count, and last-report path agree.
- [ ] No partial or obviously incomplete artifacts remain after successful generation.

**Expected:** A complete report set is present and readable.

## 6. Privacy and redaction review

**Test type:** Safe on production; review only. Use synthetic values for any deliberate redaction tests.

The redactor targets common patterns such as bearer tokens, common secret assignments, email addresses, IP/MAC addresses, UUIDs, entity IDs, URL credentials, coordinates, common home paths, and long token-like strings.

- [ ] Report JSON identifies that manual review is required.
- [ ] TXT includes a local-only/manual-review warning.
- [ ] Redaction counts are present.
- [ ] Sanitized Core log is present only when collection is enabled and available.
- [ ] No obvious secrets or personal identifiers remain.
- [ ] No original unredacted Core log is included in the ZIP.

**Expected:** Common patterns are redacted and the report warns that redaction is not guaranteed.

Do not insert real secrets into logs as test fixtures. Never share an export before manually reviewing it.

## 7. Full AI repair prompt

**Test type:** Safe on production.

Run:

```yaml
action: home_assistant_health_manager.generate_ai_repair_prompt
data:
  comprehensive: false
```

- [ ] Service succeeds.
- [ ] A fresh report and AI prompt are created.
- [ ] Event `home_assistant_health_manager_ai_repair_prompt_created` fires.
- [ ] Event contains `report_path` and `prompt_path`.
- [ ] Prompt includes diagnostic context and findings.
- [ ] Prompt requires verification of the live system and current official documentation.
- [ ] Prompt requires explicit approval before changes.
- [ ] Prompt does not contain raw unredacted log content.

**Expected:** A local, copy-ready prompt is created. Do not execute repairs as part of this test.

## 8. Focused repair prompt and investigation tracking

**Test type:** Safe on production.

A focused prompt requires a current item in the latest prioritized repair plan. If no plan item exists, record this test as blocked; do not fabricate a plan ID.

1. Inspect the attributes of the Prioritized Repair Plan Items sensor.
2. Copy an exact `plan_id`.
3. Either choose the corresponding option in **Generate Focused Repair Prompt** or run:

```yaml
action: home_assistant_health_manager.generate_focused_repair_prompt
data:
  plan_id: "REPLACE_WITH_EXACT_PLAN_ID"
```

- [ ] Focused prompt is created.
- [ ] Prompt concerns the selected plan item.
- [ ] Event `home_assistant_health_manager_focused_repair_prompt_created` includes the correct `plan_id` and `prompt_path`.
- [ ] Investigation history records the prompt.
- [ ] Generating again increments the generation count.

To update a status, first choose an item in **Investigation to Update**, then choose a status in **Investigation Status**. Alternatively:

```yaml
action: home_assistant_health_manager.set_repair_investigation_status
data:
  plan_id: "REPLACE_WITH_EXACT_PLAN_ID"
  status: "in_progress"
```

Supported values: `prompt_generated`, `in_progress`, `resolved`, `needs_follow_up`, and `dismissed`.

- [ ] Status change succeeds.
- [ ] Investigation sensor reflects the new status.
- [ ] Status update event fires.
- [ ] No Home Assistant configuration is changed.

**Expected:** Investigation tracking is persisted as user-maintained metadata. A `resolved` label is not technical proof that the underlying issue is fixed.

## 9. Ordinary restart and persistence

**Test type:** Safe on production.

Before restart, generate a report and focused prompt, set its status to `in_progress`, and record the report path and count. Restart Home Assistant normally.

- [ ] Integration loads after restart.
- [ ] Report files remain present.
- [ ] Report count and last-report metadata remain consistent.
- [ ] Investigation history and status remain.
- [ ] Focused prompt file remains.
- [ ] No duplicate report is generated merely because Home Assistant restarted.
- [ ] No report-recovery errors appear.

**Expected:** Stored report metadata and investigation history survive an ordinary restart. The selected investigation is session-only and may reset; persistent investigation history should remain.

## 10. Retention behavior

**Test type:** Safe on production for option inspection; actual expiry/deletion tests belong in a disposable environment.

- [ ] Retention option defaults to 90 days.
- [ ] Values outside 7–365 days are rejected.
- [ ] New report generation completes with the configured retention.
- [ ] Recent report artifacts remain available.

Expired-file deletion should be verified using controlled aged fixtures in a disposable instance. Do not manipulate production timestamps or delete report files to force expiry.

**Expected:** Retention is bounded and recent artifacts are preserved. Mark actual expiry deletion unverified until tested safely.

## 11. Optional native Lovelace dashboard

**Test type:** Safe on production.

Follow [docs/DASHBOARD.md](https://github.com/kraroed/home-assistant-health-manager/blob/main/docs/DASHBOARD.md). It uses native Markdown, Entities, and History Graph cards and does not require a custom frontend resource.

- [ ] Dashboard manual card saves.
- [ ] Example entity IDs are replaced where they differ.
- [ ] Health, trend, coverage, and diagnostic entities display.
- [ ] Repair plan and investigation history display.
- [ ] Focused prompt selector offers current items when available.
- [ ] Investigation selectors work.
- [ ] History graphs render.

**Expected:** Dashboard works using the actual entity IDs in this installation.

## 12. Consolidated health overview and persistent entity classifications

**Test type:** Safe on production after taking the backup described above. Use a test entity for classification-control checks; do not alter the user's established classifications merely to test the UI.

### Consolidated overview

- [ ] `sensor.health_overview` displays `healthy` or `attention` consistently with `sensor.health_status`.
- [ ] Overview attributes include active issue count, raw and actionable unknown/unavailable counts, failed/configured integration counts, platform update details, classification review queue, diagnostic coverage, compatibility, trends, and report metadata.
- [ ] Raw unknown and unavailable totals remain visible and are not reduced by classifications.
- [ ] Individual diagnostic sensors continue to work independently.
- [ ] The dashboard's Health metrics — live values card renders current values together.

### Classification workflow

- [ ] Classification records persist after a normal Home Assistant restart.
- [ ] Entering an existing entity ID loads its saved classification and reason when one exists.
- [ ] Entering a valid but not-yet-classified entity ID allows a new classification to be created.
- [ ] Applying a classification requires a non-empty explanation.
- [ ] All four values are available: `actionable`, `expected`, `setup_in_progress`, and `seasonal`.
- [ ] Applying a new classification updates the stored reason and clears stale review triggers.
- [ ] Removing a classification removes only the saved metadata and does not delete or modify the Home Assistant entity.
- [ ] Confirming a review updates its review timestamp without changing the classification or reason.
- [ ] Review interval selector supports `manual`, `30`, `60`, and `90`.
- [ ] Manual cadence still permits event-triggered review when an entity disappears, returns, changes source, or has a qualifying availability change.
- [ ] Multiple outstanding review reasons remain visible together.
- [ ] Optional persistent notifications remain disabled by default.
- [ ] When notifications are enabled, an unchanged due-entity set does not repeatedly notify; clearing the due set dismisses the notification.
- [ ] Existing user classifications are not automatically changed.

**Expected:** The overview gives a reliable single-place summary, while classifications remain explicit user-owned metadata and raw inventory metrics remain intact.

## 13. Disposable-instance fault-injection tests

**Test type:** Disposable HA OS test instance only. Never run these tests on production.

The repository contains unit tests for these transaction cases in `tests/test_report_transactions.py`. Live HA OS fault-injection remains separate evidence.

| Controlled test | Expected result |
|---|---|
| Interrupt report publication before commit | Startup removes incomplete report artifacts |
| Interrupt after Store save but before completion marker | Startup recognizes the Store-referenced report and finalizes recovery |
| Remove canonical ZIP while leaving a completion marker | Startup removes orphaned sidecars and stale marker |
| Simulate filesystem cleanup failure | Recovery marker remains so a later startup can retry |
| Simulate retention sidecar deletion failure | Canonical ZIP remains available for another cleanup attempt |
| Interrupt focused prompt creation | Uncommitted prompt artifacts are cleaned up |
| Keep a prompt referenced by investigation history | Startup preserves the committed prompt |
| Create expired report fixtures | Retention removes the expired artifact set |

- [ ] Test instance is disposable and has no important user data.
- [ ] Backup/snapshot of test instance exists.
- [ ] Fault injection is limited to test report directories.
- [ ] Each test result and relevant log is recorded.
- [ ] Test instance is restored or discarded afterward.

**Expected:** Committed artifacts survive, abandoned artifacts are cleaned up, and transient cleanup failures preserve retry markers.

## 14. Logs and troubleshooting evidence

If a test fails, capture:

- [ ] Exact step and time of failure.
- [ ] Core, Supervisor, OS, integration version, and tested commit.
- [ ] Exact error text and relevant log excerpt.
- [ ] Whether the config entry loaded.
- [ ] Whether expected sensors/select entities exist.
- [ ] Whether report artifacts were created, and which ones.
- [ ] Whether a normal restart changed the result.

Search logs for `home_assistant_health_manager`. Review import errors, config-entry failures, coordinator refresh errors, service registration errors, Store errors, filesystem errors, and recovery messages.

Redact credentials, private URLs, and personal information before sharing logs.

## 15. Upgrade, uninstall, and reinstall

**Test type:** Prefer disposable instance. If performed on production, take a fresh full backup first.

Upgrade:
- [ ] Record current version and commit.
- [ ] Back up Home Assistant.
- [ ] Install the target revision using HACS.
- [ ] Restart normally.
- [ ] Confirm integration loads and entities retain their unique IDs.
- [ ] Confirm report files and investigation history remain.
- [ ] Check for migration/setup errors.

Uninstall/reinstall:
- [ ] Back up report files if they should be retained.
- [ ] Remove the config entry through Devices & services.
- [ ] Confirm entities unload and integration services are removed when the last entry unloads.
- [ ] Confirm Home Assistant starts normally.
- [ ] Reinstall and confirm setup works if testing reinstall.

Do not manually delete `/config/health_manager` on production to test removal.

## 16. Results record

Copy and complete this block:

```text
HOME ASSISTANT HEALTH MANAGER — HA OS TEST

Test date:
Home Assistant Core:
Supervisor:
Home Assistant OS:
Integration version:
Git commit:

INSTALLATION
[ ] Backup completed
[ ] HACS installation successful
[ ] Restart successful
[ ] Config flow successful
[ ] Options flow successful

DIAGNOSTICS
[ ] Expected sensors created
[ ] Seven select entities created
[ ] Two text entities created
[ ] Two button entities created
[ ] Health Overview sensor verified
[ ] First report generated
[ ] JSON inspected
[ ] TXT inspected
[ ] ZIP inspected

PRIVACY
[ ] Manual-review warning present
[ ] Redaction manually reviewed
[ ] No obvious secrets exposed
[ ] Sanitized log behavior checked

PROMPTS AND TRACKING
[ ] Full AI prompt generated
[ ] Focused prompt generated
[ ] Investigation recorded
[ ] Status update successful
[ ] Status survived restart

PERSISTENCE AND RETENTION
[ ] Ordinary restart successful
[ ] Report metadata retained
[ ] Investigation history retained
[ ] Retention settings verified
[ ] Expiry tested in disposable instance
[ ] Fault-injection tests completed in disposable instance

DASHBOARD
[ ] Dashboard added
[ ] Entity IDs adjusted
[ ] Cards and selectors work

UPGRADE / UNINSTALL
[ ] Upgrade tested
[ ] Uninstall tested
[ ] Reinstall tested

RESULT: PASS / PASS WITH ISSUES / FAIL / INCOMPLETE

Issues:
Relevant logs/evidence:
Next action:
```

## Beta testing release gate

The beta exists specifically to enable controlled installation and live testing. Do not require live HA OS test results before publishing this clearly labeled pre-release; those results are the purpose of the beta.

Before publishing `0.1.0-beta.1`, verify:

1. The manifest version is exactly `0.1.0-beta.1` and the Git tag uses the same value.
2. The release is explicitly marked **pre-release** in GitHub.
3. The release notes identify this as an initial testing beta and state that live HA OS validation is outstanding.
4. The latest GitHub Actions run passes all Python tests, hassfest, and HACS validation on the exact tagged commit.
5. The HACS brand icon, README, license, manifest, and `hacs.json` are present.
6. The repository contains this installation checklist and the test instance has a full backup before installation.
7. No unresolved release-blocking defect is known. In particular, report artifacts must be readable and the privacy warning must remain prominent.

A successful beta release does not mean runtime validation is complete or that the integration is suitable for unattended production use.

## Stable release gate

Do not declare the integration runtime-tested or ready for a stable release until:

1. Installation and setup pass on a real HA OS instance.
2. First diagnostic report and all artifacts are generated and readable.
3. Privacy warnings and manual redaction review are satisfactory.
4. Full and focused prompt workflows work.
5. Investigation status survives restart.
6. Ordinary startup recovery preserves valid reports.
7. Retention and fault-injection behavior are verified in a disposable instance.
8. No unresolved high-severity integration errors remain.
9. GitHub Actions validation passes on the exact stable release commit.

A successful CI run alone is not live Home Assistant OS validation.
