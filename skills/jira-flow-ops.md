---
name: jira-flow-ops
description: Orchestrates exporting data from Jira and generating datasets for the local Flow Coaching Dashboard. Use when the user asks to "run the export" or update flow metrics data.
metadata:
  version: 1.1.0
---

# Jira Flow Ops

## Outcome
Generate updated workflow, sprint, dependency, and blocked-history datasets from a Jira instance so they can be loaded into the Flow Coaching Dashboard.

## Prerequisites
- `jira_export.py` script located in the repository root.
- Python dependencies: `requests`
- Jira API Credentials (`JIRA_BASE_URL`, `JIRA_USER`, `JIRA_API_TOKEN`).
- A target `JQL` query defining the scope of the export.

## Process

1. **Verify Credentials**: Check if `JIRA_BASE_URL`, `JIRA_USER`, and `JIRA_API_TOKEN` are set in the environment. 
   - If missing, use the `bws` skill to fetch the token from Bitwarden. If the user hasn't provided the base URL or JQL, ask them for the query parameters.
2. **Execute Export**: Run the export script, passing the target JQL and output directory.
   ```powershell
   python jira_export.py --jql "issuetype in (Story, Bug, Epic) AND project NOT IN (ARCHIVED)" --out-dir "C:\Path\To\Customer_Folder"
   ```
   > **Note on JQL & API**: When extracting across spaces, exclude standard `Task` items unless explicitly requested, as they can pull in thousands of non-dev subtasks. If the export encounters a `410 Gone` error, ensure the repository's `jira_export.py` is updated to use the modern `/rest/api/3/search/jql` endpoint instead of the deprecated `/rest/api/3/search`.
3. **Verify Output**: Confirm the script generated the 5 required files in the output directory:
   - `flow_analytics_export.csv`
   - `issue_metadata.csv`
   - `sprint_data.csv`
   - `issue_links.csv` (Dependency mapping)
   - `flag_history.csv` (Impediment tracking)
4. **Load into Dashboard**: Instruct the user to open the dashboard (`npm start` if not already running) and drag the generated output folder into the dropzone to visualize the updated metrics.

## Notes for Agents
- The dashboard operates entirely client-side (in the browser). Agents do not push data *into* the dashboard directly; they generate the CSV files, and the user drops the folder into the UI.
- If the user asks to analyze bottlenecks or dependencies natively in the terminal, you can parse `issue_links.csv` and `flag_history.csv` using Python (`pandas`) directly.
