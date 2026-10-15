# Daily Jira Refresh Spec and Plan

Date: 2026-06-20
Workspace: `<repo-root>`
Status: Draft for review

## Problem Statement

The dashboard is useful only when its CSV input folder reflects current Jira reality. Today, freshness depends on a manual terminal export and then a manual folder load in the browser. The efficient target is a daily, auditable data-refresh pipeline that keeps the expected CSV folder current without changing the dashboard into a backend application.

## Recommended Direction

Keep the dashboard static and client-side. Automate a daily export pipeline that:

1. Treats each consultant-managed data folder as a self-contained source with its own config, refresh state, snapshots, and `latest` dataset.
2. Creates the initial dataset with a full export.
3. Uses Jira's `updated` field to fetch changed issues on normal daily runs.
4. Merges changed issue records into a copy of the previous validated dataset.
5. Reconciles current scope and periodically performs a full refresh to prevent stale or missing records.
6. Writes a dated immutable snapshot.
7. Updates a stable `latest` dataset folder for the dashboard user to load.
8. Produces a manifest, validation report, and log so failures are visible.
9. Keeps customer Jira data out of git by default.

This is the lowest-friction architecture because it respects the current repo model: `index.html` / `js/app.js` parse user-selected CSV files, while `jira_export.py` and `export_sprint_data.py` own Jira extraction.

## User Scenarios

### P1 - Daily dataset is ready before work starts

As a flow coach, I want a fresh Jira CSV folder generated every morning so I can open the dashboard and immediately review current flow, sprint, dependency, blocker, and optional value data.

Test notes:
- A scheduled run creates `snapshots/YYYY-MM-DD/` with required CSVs.
- A stable `latest/` folder contains the same validated CSVs.
- The manifest records run time, JQL, Jira base URL host, issue count, row counts, and status.

### P1 - Failures are obvious and diagnosable

As the person maintaining the dashboard, I want failed refreshes to leave clear evidence so I do not accidentally coach from stale data.

Test notes:
- Failed runs do not overwrite `latest/`.
- A failed manifest/log records the failed step and error.
- Validation flags missing files, empty critical files, stale snapshots, and suspicious row-count drops.

### P1 - Daily refresh avoids unnecessary full-history pulls

As a consultant working with a large Jira scope, I want normal daily runs to retrieve only changed issues so refreshes consume less API capacity and finish faster.

Test notes:
- The first run performs a full export.
- A normal run adds a bounded clause such as `updated >= "<watermark minus overlap>"` to the folder's base JQL.
- The successful-run watermark advances only after validation and promotion complete.
- Rows for changed issues replace their previous rows by `Issue Key`; unchanged issues remain intact.
- The manifest records whether the run was `full`, `incremental`, or `reconciliation`, plus issue and row counts.

### P2 - Customer datasets remain independent

As a consultant, I want to run the same refresh tool from different customer data folders without those folders knowing about or coordinating with each other.

Test notes:
- Each folder contains its own non-secret refresh config and state.
- Running the tool against one folder reads and writes only that folder.
- No central source registry or `--all` orchestration is required.
- Secrets are read from environment or Bitwarden, not stored in the folder config.

### P2 - Sprint data is reliable

As a dashboard user, I want sprint charts to stay useful even when Jira's `customfield_10020` is empty.

Test notes:
- The pipeline can run `export_sprint_data.py` with a configured `board_id`.
- When sprint fallback succeeds, it overwrites or replaces `sprint_data.csv` from the main exporter.
- Kanban boards that return 400 are skipped and reported without failing unrelated sources.

### P3 - Optional value analytics can be refreshed

As a flow coach, I want outcome/value analysis available when configured, without making it a hard dependency for basic flow metrics.

Test notes:
- A source config can enable value analysis.
- If enabled, `issue_value_analysis.csv` is generated or carried forward according to explicit policy.
- If disabled or failed, the manifest says value analytics are unavailable while core flow files remain usable.

## Functional Requirements

1. Each customer/scope data folder contains a local config, preferably `refresh.json`, with:
   - `name`
   - `jira_base_url_env` or default `JIRA_BASE_URL`
   - `jira_user_env` or default `JIRA_USER`
   - `jira_token_env` or default `JIRA_API_TOKEN`
   - immutable or broadly stable `base_jql`
   - optional `board_id`
   - optional `batch_size`
   - optional `enable_value_analysis`
   - optional `incremental_overlap_minutes`
   - optional `full_refresh_interval_days`
   - optional `retention_days`
2. Each data folder contains a generated state file, preferably `refresh-state.json`, recording:
   - last successful run start and completion timestamps
   - last successful full refresh timestamp
   - last promoted snapshot
   - base JQL/config fingerprint
3. Add a wrapper script, tentatively `daily_refresh.py`, that operates on one supplied data folder and orchestrates:
   - credential/environment checks
   - main `jira_export.py`
   - optional sprint fallback via `export_sprint_data.py`
   - optional value analysis
   - incremental merge
   - scope reconciliation
   - validation
   - snapshot promotion to `latest`
   - manifest/log writing
4. Support explicit `full`, `incremental`, and `validate-only` modes; default to incremental only when a valid previous snapshot and watermark exist.
5. Construct incremental JQL from the folder's base JQL and the last successful watermark, with a configurable overlap window to tolerate timestamp precision, indexing delay, interrupted runs, and clock skew.
6. Merge CSV data by issue ownership:
   - one-row-per-issue files replace the row for each changed `Issue Key`
   - multi-row files remove all rows owned by each changed issue before inserting the new rows
   - unchanged issue rows are copied from the previous validated snapshot
7. Run a lightweight current-scope inventory, requesting issue keys for the full base JQL, so issues that were deleted, moved, or no longer match mutable scope criteria can be removed from the merged dataset.
8. Do not rely solely on the issue `updated` watermark for sprint data. Refresh sprint metadata/membership independently, or use an explicitly tested incremental sprint strategy, because sprint state can change without every member issue being updated.
9. Perform a periodic full refresh as a correctness backstop and whenever the base JQL/config fingerprint changes.
10. Write outputs to a gitignored customer-data path, not into source-controlled repo files.
11. Create immutable snapshots before promoting to `latest`.
12. Promote `latest` and advance the watermark only after validation passes.
13. Keep the dashboard loading model unchanged for the first increment: the user still selects the generated `latest` folder.
14. Provide scheduler examples for Windows Task Scheduler and macOS/Linux cron or launchd.
15. Provide a dry-run or validate-only mode so configs can be checked without overwriting `latest`.

## Success Criteria

1. A daily run can be scheduled without manually typing JQL or output paths.
2. The dashboard can be refreshed by selecting one stable `latest` folder.
3. A failed Jira API call does not silently replace yesterday's working data.
4. Validation catches missing required CSVs and empty critical exports.
5. The run produces enough manifest data to answer: when was this refreshed, what query was used, how many issues/rows were exported, and was sprint/value data complete?
6. Customer data remains out of git by default.
7. After the initial full export, a normal daily run retrieves detailed Jira data and changelogs only for issues updated since the prior successful run, including the overlap window.
8. Incremental output is equivalent to a full export for the same point in time, within documented Jira indexing and sprint-refresh constraints.
9. Running a refresh for one customer folder cannot read, modify, or coordinate with another customer folder.

## Conviction Level

High for automating daily CSV generation with a wrapper and scheduler.

Medium for optional auto-loading in the browser, because browser folder access and client-side security constraints make this more complex than the value justifies for the first increment.

## Leap Of Faith Assumptions

Value:
- Daily freshness materially improves dashboard usefulness compared with ad hoc exports.
- A stable `latest` folder is enough friction reduction for the near term.

Usability:
- Selecting a `latest` folder in the dashboard is acceptable if the data generation itself is automated.
- Users will trust the data more if the dashboard or folder includes a clear manifest timestamp.

Feasibility:
- The existing `jira_export.py` reliably exports core CSVs through `/rest/api/3/search/jql`.
- `export_sprint_data.py` with `board_id` covers instances where sprint custom fields are empty.
- Jira JQL supports date comparisons on the `updated` field, enabling incremental issue selection.
- Correct incremental output requires deterministic CSV merge rules, scope reconciliation, and independent sprint handling; the JQL clause alone is not sufficient.
- Windows Task Scheduler can run the refresh with the right environment variables or a small `.ps1` launcher.

Viability:
- Keeping customer data local or in the customer's approved Drive folder avoids new security/review burden.
- GitHub Actions is only viable if storing Jira credentials and customer data as CI artifacts is acceptable for the specific client.

## Technical Plan

Execution strategy: delivery-oriented for the local scheduled CSV pipeline. Implement correctness-first full refresh and atomic promotion before enabling incremental mode. Defer browser auto-load as a separate learning slice.

### Incremental Refresh Decision

Jira can select recently changed issues with JQL:

```text
(<base JQL>) AND updated >= "<last successful run minus overlap>"
ORDER BY updated ASC
```

Use an absolute persisted timestamp rather than only a relative expression such as `-1d`. A relative expression can leave gaps after missed or delayed runs. The overlap window intentionally re-fetches a small number of issues; merging by issue key makes this idempotent.

The `updated` clause is enough to identify most changed issue records, including field, status, link, flag, and comment changes. It is not enough by itself for a correct long-lived dataset:

- An issue moved or changed so it no longer matches the base JQL will not appear in `(<base JQL>) AND updated >= ...`; a current-scope key inventory or full reconciliation must remove it.
- Deleted or newly inaccessible issues need the same reconciliation.
- Sprint state, dates, and membership can change independently of each issue's `updated` timestamp.
- A failed or partial run must not advance the watermark.
- A changed issue must replace all of its derived rows, not be appended blindly.

Recommended operating model:

1. Full bootstrap.
2. Daily incremental issue refresh with an overlap window.
3. Daily lightweight scope-key reconciliation.
4. Independent sprint refresh.
5. Weekly full refresh initially; relax the cadence after production evidence shows the incremental output remains equivalent.

This adds moderate implementation complexity, mainly in merge/reconciliation logic and tests, but is justified for large projects because it avoids repeatedly downloading full issue payloads and histories. The scope-key inventory still scans the full scope, but requests only keys and is substantially lighter than a full fields-plus-changelog export.

### Increment 1 - Correct Full Refresh And Folder Isolation

Add:
- `refresh.example.json`
- `daily_refresh.py`
- `validate_export.py` or validation inside `daily_refresh.py`
- docs section in `README.md`

Flow:
1. Load config from the supplied customer data folder.
2. Resolve env vars and fail fast if required Jira credentials are missing.
3. Create run directory: `<data-folder>/snapshots/YYYY-MM-DD/`.
4. Run `jira_export.py --jql ... --out-dir <snapshot> --batch-size ...`.
5. If `board_id` is configured, run `export_sprint_data.py --jql ... --board-id ... --out <snapshot>/sprint_data.csv`.
6. If value analysis is enabled, run the value-analysis step against the snapshot.
7. Validate required files:
   - `flow_analytics_export.csv`
   - `issue_metadata.csv`
   - `sprint_data.csv`
   - `issue_links.csv`
   - `flag_history.csv`
   - optional `issue_value_analysis.csv`
8. Write `manifest.json` and `refresh.log`.
9. Replace `<data-folder>/latest/` with a copy of the validated snapshot.
10. Apply retention cleanup only after successful promotion.

### Increment 2 - Daily Incremental Refresh

1. Read the previous validated snapshot and watermark.
2. Capture the new run-start timestamp.
3. Build delta JQL from the base JQL plus `updated >= <previous watermark minus overlap>`.
4. Export complete current fields and required history for changed issues.
5. Copy the previous snapshot into a candidate snapshot.
6. Replace changed issue rows according to file-specific merge rules.
7. Run a key-only base-JQL inventory and remove keys no longer in scope.
8. Refresh sprint data independently.
9. Validate the candidate snapshot against structural checks and suspicious-change thresholds.
10. Atomically promote the candidate and persist the run-start timestamp as the next watermark.

For high-volume history retrieval, evaluate Jira's bulk changelog endpoint rather than depending on expanded changelogs in every search result. Atlassian documents bulk changelog retrieval for up to 1,000 issues per request and optional field filtering.

### Increment 3 - Staleness Signal In The Dashboard

Add dashboard support for reading an optional `manifest.json` from the loaded folder. Show:
- last refreshed timestamp
- source name
- issue count
- warning if data is older than configured threshold

This still keeps the dashboard client-side and file-driven.

### Increment 4 - Optional Hosted Or CI Refresh

Only if client/security constraints allow it:
- Run the same one-folder refresh command from GitHub Actions or another runner.
- Store credentials as runner secrets.
- Publish encrypted/private artifacts or sync to an approved Drive/customer folder.

This should not be the default because customer Jira exports are sensitive and the current architecture does not require a hosted backend.

## Scheduler Recommendation

Default Windows approach:
- Create a PowerShell launcher, e.g. `scripts/refresh-jira-flow.ps1`.
- It sets or imports required env vars, activates Python if needed, runs:

```powershell
python daily_refresh.py --data-dir "H:\...\Customer\jira-flow-data"
```

- Register it in Windows Task Scheduler for early morning local time.

Cross-machine notes:
- macOS/Linux can use cron or launchd with the same `daily_refresh.py`.
- Each scheduled command targets one independent data folder.
- Avoid storing machine-specific output paths inside the folder config when the folder itself can be treated as the output root.

## Official Jira References

- JQL comparison operators, including date-field `>=`: https://support.atlassian.com/jira-software-cloud/docs/jql-operators/
- Jira example of a recently updated filter using `updatedDate >= -1d`: https://support.atlassian.com/jira-software-cloud/docs/configure-quick-filters/
- Enhanced JQL search API with `nextPageToken`: https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/
- Bulk issue changelog retrieval: https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-changelog-bulkfetch-post

## Test Strategy

Testing must prove that incremental refresh is equivalent to a full refresh, not merely that individual helper functions execute.

### Unit Coverage

- Config and state parsing, defaults, invalid values, and config-fingerprint changes.
- Incremental JQL generation, timestamp formatting, overlap-window behavior, and parenthesizing of complex base JQL.
- Merge behavior for every CSV:
  - replacing one-row-per-issue records
  - replacing all multi-row records owned by a changed issue
  - adding newly created issues
  - removing issues absent from the scope inventory
  - preserving unchanged issues byte-for-byte where practical
- Watermark rules: advance only after successful validation and promotion.
- Snapshot naming, retention decisions, manifest counts, and staleness calculations.

### Fixture-Based Pipeline Coverage

Maintain small deterministic before/delta/expected-full fixture sets covering:

- no changes
- one field/status change
- multiple transitions inside the overlap window
- a newly created issue
- an issue leaving the base JQL
- a deleted or inaccessible issue
- link addition and removal
- flag addition and removal
- sprint membership and sprint-state changes
- empty optional files and disabled value analysis
- overlapping reruns that fetch the same issue more than once

For each fixture, run the incremental merge and assert that all resulting CSVs and manifest counts match the expected full-export snapshot after canonical row sorting.

### Fault-Injection And Atomicity Coverage

Simulate failures during Jira pagination, changelog retrieval, sprint export, CSV writing, validation, promotion, and state-file writing. Assert that:

- the previous `latest` directory remains loadable and unchanged
- the previous watermark remains unchanged
- incomplete candidate snapshots are never promoted
- retrying the same run is idempotent
- logs and manifests identify the failed stage without exposing credentials

### Jira Contract Coverage

- Mock paginated `/rest/api/3/search/jql` responses including `nextPageToken`, empty pages, 429 retry handling, 5xx retries, and malformed payloads.
- Mock bulk-changelog pagination and field filtering if that endpoint is adopted.
- Verify requested search fields are minimal and intentional.
- Keep an opt-in live smoke test for a small non-production Jira scope; never require customer credentials in CI.

### Cross-Platform And Scheduler Coverage

- Run unit and fixture tests on Windows and a Unix runner in CI.
- Verify paths with spaces and platform-specific separators.
- Test the PowerShell launcher without depending on an interactive shell profile.
- Validate documented cron/launchd commands through argument-construction tests even when those schedulers are not available in CI.

### Performance And Scale Coverage

- Generate synthetic fixtures representing at least 10,000 issues with a small daily delta.
- Measure full versus incremental API request counts, transferred issue payloads, merge time, and peak memory.
- Set a regression budget after the first benchmark. The incremental path should scale mainly with the changed-issue count plus the lightweight scope-key inventory, rather than full issue-history volume.

### Release Gates

Incremental mode is not production-ready until:

1. All unit, fixture, fault-injection, and cross-platform tests pass.
2. Full-versus-incremental equivalence passes across the complete fixture matrix.
3. A live smoke test succeeds against a small approved Jira scope.
4. At least one shadow run compares incremental and full outputs without promoting incremental output.
5. Any differences are explained, fixed, or explicitly documented before daily scheduling is enabled.

## Open Decisions

1. What overlap window should be the default: 10 or 15 minutes?
2. Should the initial full-reconciliation cadence be weekly or based on a maximum incremental-run count?
3. Should value analytics be part of daily incremental refresh immediately, or remain full-refresh/manual until the core flow merge is reliable?
4. Is a dashboard-visible manifest/staleness banner worth doing in the first implementation pass?

## Definition Of Done

1. `daily_refresh.py --data-dir <folder> --full` creates a valid snapshot and promotes `latest`.
2. `daily_refresh.py --data-dir <folder>` performs an incremental refresh when valid state exists and falls back to full refresh otherwise.
3. `daily_refresh.py --data-dir <folder> --validate-only` verifies the current latest/snapshot without Jira access.
4. Incremental output matches a same-time full export in automated fixture tests, including updated issues, newly created issues, issues leaving scope, and failed-run recovery.
5. Each folder is independently operable and contains no references to other customer folders.
6. The generated `latest` folder loads in the dashboard through the existing folder picker.
7. Failed refreshes leave yesterday's `latest` and watermark intact.
8. README documents setup, config, full/incremental runs, reconciliation, and scheduling.
9. Tests cover config loading, per-file merge semantics, scope removals, sprint refresh behavior, validation failure, successful promotion, and no-overwrite/no-watermark-advance on failure.
