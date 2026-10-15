# Agent Guidelines for Jira Flow Coaching Dashboard

Welcome! If you are an AI assistant or autonomous agent working in this repository, here is how the architecture and workflows function.

## Architecture & Data Flow

1. **Client-Side Rendering:**
   The `index.html` dashboard runs entirely client-side. It does not have a backend server or a direct database connection. All analytics, aggregations, and charts (via Chart.js) are calculated in the browser.
2. **Data Ingestion via CSV Dropzone:**
   The dashboard expects users to provide the data manually via a drag-and-drop folder interface. The necessary dataset consists of six CSV files exported from a Jira instance:
   - `flow_analytics_export.csv`
   - `issue_metadata.csv`
   - `sprint_data.csv`
   - `issue_links.csv`
   - `flag_history.csv`
   - `issue_value_analysis.csv` (optional, for value analytics)
3. **Data Extraction Pipeline (`jira_export.py`):**
   The source of truth for generating these CSVs is the `jira_export.py` script. This script interfaces with the Jira REST API using environment-provided credentials (`JIRA_BASE_URL`, `JIRA_USER`, `JIRA_API_TOKEN`) and extracts a given `JQL` query into the required CSV schema.

---

## 1. Required Credentials & Instance Profiles

The exporter script requires three environment variables to be set before running:

```bash
export JIRA_BASE_URL="https://your-domain.atlassian.net"
export JIRA_USER="your-email@example.com"
export JIRA_API_TOKEN="your-api-token"
```

### Instance Profiles
Keep customer instance URLs, identities, JQL scopes, and output paths outside this
repository. Set the environment variables above and pass `--jql` and `--out-dir`
to `jira_export.py` explicitly. Never commit credentials or customer exports.

---

## 2. Exporter Script Setup & Execution

### Prerequisites
Make sure the target machine has Python 3 and the `requests` library:
```bash
pip install requests
```

### Running the Exporter
Once environment variables are set, execute the script by providing a JQL query and the output directory:

```bash
python3 jira_export.py --jql "project = 'PROJ' AND issuetype in (Story, Bug)" --out-dir my_jira_data
```

This generates the required CSV files inside the `my_jira_data` folder.

---

## 3. Launching the Dashboard

1. Start the local server:
   ```bash
   npm start
   ```
2. Open your web browser to `http://localhost:3000`.
3. Click the **Load Data Folder** drop zone and select the `my_jira_data` folder.

---

## Core Workflows for Agents

### 1. Generating Data
When tasked to "run the export" or "fetch updated data" for a customer:
- **Do not** attempt to push data directly into the dashboard DOM or bypass the dropzone.
- **Do** invoke the local `jira-flow-ops` skill (located in `skills/jira-flow-ops.md`). This skill outlines the exact terminal command required to run `jira_export.py`.
- **Do** utilize the `bws` (Bitwarden Secrets Manager) skill to securely fetch the `JIRA_API_TOKEN` if it is not present in the environment variables.
- Prompt the user for the target output directory and `JQL` query if they are not explicitly provided or discoverable in their context (e.g., in a `sources/` customer folder).

### 2. Modifying Dashboard Visualizations
When asked to add a new chart or modify an existing one:
- All charting logic is located within `index.html`.
- Ensure new data requirements are first added to the extraction layer (`jira_export.py`) and appropriately parsed within `index.html`'s `PapaParse` and `processData` hooks.
- Adhere to the established CSS variable color systems (e.g. `getCategoryColor`) for consistency across Epoch, Control, and Dependency charts.

### 3. Modifying Dependency Tracking
The `issue_links.csv` and `flag_history.csv` files are utilized strictly for dependency and blocker analytics. 
- **Dependencies** are built by scanning outward/inward links (`blocks`, `is blocked by`). 
- **Blockers** are tracked by identifying changes to the custom `Flagged` field in the changelog.
- Any new dependency algorithms (like longest-blocked-path) should be implemented directly in Javascript within `renderDependencyAnalysis()`.

### 4. Troubleshooting Jira API Access (Lessons Learned)
When extracting data for clients (e.g., a large client) or testing the pipeline, keep the following quirks in mind:
- **Atlassian Endpoint Deprecation:** If you encounter `410 Gone` HTTP errors when attempting to search Jira, this is because Atlassian removed the classic `/rest/api/3/search` endpoint. Always use `/rest/api/3/search/jql` and be prepared to handle `nextPageToken` pagination rather than `startAt`/`maxResults`.
- **Constructing JQL for 'All Work':** When a user asks to pull "all spaces except archived ones", use `project NOT IN (ARCHIVED)` rather than `projectCategory != "Archived"` (as many projects lack categories). Additionally, excluding `Task` from your `issuetype in (...)` filter is often necessary for enterprise clients to avoid pulling in tens of thousands of irrelevant non-dev tasks.
- **PowerShell curl Hangs:** When debugging endpoints manually via terminal on Windows, the default `curl` command is an alias for `Invoke-WebRequest`. This will often hang indefinitely when it hits Atlassian's complex web portal redirects. Always explicitly use `curl.exe` to bypass the PowerShell alias.
- **Sprint Data via Agile Board API:** The `customfield_10020` sprint field in `/rest/api/3/search/jql` returns null on many instances. Use the Agile board API (`/rest/agile/1.0/board/{id}/sprint` + `/rest/agile/1.0/sprint/{id}/issue`) instead. See `export_sprint_data.py` for the working implementation.
- **Kanban Boards Return 400:** Boards that are Kanban-type (not Scrum) return HTTP 400 when querying sprints. Catch and skip these gracefully.

### 5. Cloudflare & Deployment Ops
- **Proactive Execution:** Whenever suggesting Cloudflare infrastructure, Pages, Workers, or deployment configurations, directly execute and automate the deployment end-to-end (via `bws` secrets, `wrangler`, GitHub Actions, or API) rather than presenting manual web UI instructions.

