# Jira Flow Coaching Dashboard

Public source: [yyeret/jira-flow-coaching-dashboard-public](https://github.com/yyeret/jira-flow-coaching-dashboard-public). Licensed under [ISC](LICENSE).

This dashboard is designed to help teams and organizations manage and visualize flow metrics following the [Kanban Guide for Scrum Teams](https://scrum.org/resources/kanban-guide-scrum-teams) (co-authored by Yuval Yeret) and Yuval Yeret's Flow Coaching methodology. It enables flow optimization for teams using Jira at both the story and epic level, prioritizing finishing over starting, descaling, and focusing on flow over resource utilization.

For background on the core mechanics and measurements, refer to:
- [The Kanban Guide for Scrum Teams](https://scrum.org/resources/kanban-guide-scrum-teams) (Official Scrum.org Guide)
- [The 4 Flow Metrics for Scrum Teams](https://www.scrum.org/resources/4-flow-metrics-scrum-teams-kanban) (WIP, Cycle Time, Throughput, Work Item Age)
- [Yuval Yeret's Flow Coaching Resources](https://yuvalyeret.com/)

## Core Flow Principles

- **Stop Starting, Start Finishing:** Limit Work in Progress (WIP) to stabilize flow and uncover bottlenecks.
- **Leading over Lagging:** Pay close attention to Work Item Age (a leading indicator of SLA breaches) rather than just Cycle Time.
- **Count-based Throughput:** Forecast delivery rates using exact counts of finished items rather than story points.

## Setup and privacy

Use Node.js 22+ and Python 3.11+. Install dependencies before running:

```bash
npm ci
python3 -m pip install -r requirements.txt
```

`npm start` builds and serves only the public bundle on `http://127.0.0.1:3000`.
The CSV analysis runs in your browser. Selected data is cached locally until you
click **Clear saved data**. Optional AI coaching sends selected metrics and names
to Google Gemini after confirmation; see [Security and data handling](SECURITY.md).
Keep real Jira exports outside this repository. `sample_data/` contains generated
demonstration scenarios from `simulate_flow.py`.

## Using the Dashboard

To run the dashboard as a local web server:

1. Open a terminal in the project directory.
2. Run the command `npm start`.
3. Open your browser to the local URL provided (usually `http://localhost:3000`).
4. Click **"Load Data Folder"** or click on the upload drop zone to select your data folder.
5. Select the folder containing the CSV files described below.
6. The dashboard will automatically parse the files and populate the Cumulative Flow Diagram, Control Chart, Work Item Age, and Throughput charts.

## Required Data Structure

The dashboard expects a folder containing the following five CSV files:

### 1. `flow_analytics_export.csv`
Contains the core issue information and timestamp data for each workflow state.
**Required Columns:** `Issue Key`, `Summary`, `Issue Type`, `Created Date`, `Updated Date`, `Current Status`, plus one column for *each* state in your workflow containing the timestamp when the issue entered that state.

### 2. `sprint_data.csv`
Contains sprint membership data to power the Sprint Predictability & Carryover chart.
**Required Columns:** `Issue Key`, `Sprint ID`, `Sprint Name`, `Sprint State`, `Start Date`, `End Date`, `Added Mid-Sprint`

### 3. `issue_metadata.csv`
Contains label and metadata for filtering.
**Required Columns:** `Issue Key`, `Labels`

### 4. `issue_links.csv`
Contains inward and outward links used to build the Dependency tree.
**Required Columns:** `Source Issue Key`, `Link Type Name`, `Direction`, `Target Issue Key`

### 5. `flag_history.csv`
Contains changelog history of the custom 'Flagged' field to build Blocked/Impediment timelines.
**Required Columns:** `Issue Key`, `Flag Added Date`, `Flag Removed Date`, `Days Blocked`

Optional `issue_parents.csv` and `issue_value_analysis.csv` enrich epic relationships and value analysis.

## Generating the Data

### Option A: Using the CLI Exporter Script (Recommended)
You can use the provided Python script to automatically fetch this data directly from your Jira instance via the REST API.

**Prerequisites:**
```bash
python3 -m pip install -r requirements.txt
```

**Setup Environment Variables:**
```bash
export JIRA_BASE_URL="https://your-domain.atlassian.net"
export JIRA_USER="your-email@example.com"
export JIRA_API_TOKEN="your-api-token"
```

**Run the Script:**
```bash
python3 jira_export.py --jql 'project = "PROJ" AND issuetype in (Story, Bug, Epic)' --out-dir ../my_jira_data
```
This will create `../my_jira_data/flow_analytics_export.csv`, `../my_jira_data/sprint_data.csv`, and `../my_jira_data/issue_metadata.csv` (along with dependencies/flag history). You can then load the `my_jira_data` folder into the dashboard.

> **Troubleshooting `410 Gone` Errors**: Atlassian recently deprecated the classic `GET /rest/api/3/search` endpoint. Ensure you are using the latest version of `jira_export.py`, which has been updated to use the new `/rest/api/3/search/jql` endpoint and its `nextPageToken` pagination system.


## Development and deployment

```bash
npm run lint
npm test
npm run build
npm run audit:release
```

The build copies an explicit asset list into `dist/` and bundles locked browser
libraries with their license notices. Deploy **only `dist/`**. The Cloudflare
workflow is manual and disabled by default. To enable it for your own deployment,
set repository variables `ENABLE_PAGES_DEPLOY=true` and `CLOUDFLARE_PAGES_PROJECT`
to your own Pages project name, and provide repository secrets
`CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`. The deployment uses `_headers`.

The package is marked private to prevent accidental npm publication. The source
is licensed under [ISC](LICENSE); bundled dependencies retain their own notices.
See the [publication audit](docs/public-readiness-audit.md) before changing the
visibility of a repository with existing history.
