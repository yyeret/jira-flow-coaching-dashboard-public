---
name: flow-copilot
description: Flow Coaching Copilot tool. Provides command-line and agentic (MCP) access to flow metrics, sprints, dependencies, blockers, and value taxonomy classifications directly from local Jira data folder.
metadata:
  version: 1.0.0
---

# Flow Coaching Copilot

## Outcome

Allow AI agents and users to programmatically interact with and query flow metrics (WIP, Age, Cycle Time, Sprints, Blocker analytics) and outcome taxonomies from local Jira data directories.

## CLI Usage

Run `flow_copilot.py` with Python and select one of the command flags. By default, it looks in the current directory for the 5 Jira CSV files:

```bash
# High level metrics health check (WIP counts, completed counts, average cycle times, 85th percentiles)
python flow_copilot.py summary --data-dir my_jira_data

# Aging active Work in Progress items sorted by age
python flow_copilot.py wip --data-dir my_jira_data

# Active and historical blocker / flagged reasons and cumulative duration
python flow_copilot.py blockers --data-dir my_jira_data

# Blocking and blocked by dependency links
python flow_copilot.py dependencies --data-dir my_jira_data

# Sprints planned vs completed count and points
python flow_copilot.py sprints --data-dir my_jira_data

# Value/Outcome Taxonomy distribution and Epic framing
python flow_copilot.py outcomes --data-dir my_jira_data

# Innovation Rate: value vs. failure demand (rework) vs. maintenance/filler (EBM Ability to Innovate)
python flow_copilot.py innovation --data-dir my_jira_data

# Defect trend: failure-demand items created per time bucket, with a rising/falling slope
python flow_copilot.py defects --data-dir my_jira_data

# Per-stage time breakdown (median/p85 days) for completed items
python flow_copilot.py stage-times --data-dir my_jira_data

# Cumulative value delivered, actual vs. ideal sequencing. Value signal degrades
# gracefully: Cost of Delay -> Priority field -> backlog Rank -> FIFO arrival order.
python flow_copilot.py value-curve --data-dir my_jira_data

# Get opinionated coaching insights and recommendations
python flow_copilot.py coaching --data-dir my_jira_data
```

Work Class (`Value` / `Failure Demand` / `Maintenance`) and `Cost of Delay` are read
from the `issue_metadata.csv` columns when present (the simulator emits them); for real
Jira exports without those columns, Work Class is inferred from issue type (`Bug`) and
labels (`regression`, `filler-techdebt`, etc.).

## Model Context Protocol (MCP) Mode

To start the Copilot as an MCP server via stdio:

```bash
python flow_copilot.py mcp --data-dir my_jira_data
```

Once started, the server exposes the following tools:
1. `get_summary`: Return overall flow counts, average cycle times, and 85th confidence level.
2. `get_wip`: Return all active WIP issues and their elapsed age in days.
3. `get_blockers`: Return active/historical blocker events with classification mapping.
4. `get_dependencies`: Return blocking/blocked mapping pairs.
5. `get_sprints`: Return structured sprint data showing planned/completed count/points.
6. `get_outcomes`: Return value taxonomy counts and suggested epic outcome framing.
7. `get_innovation_rate`: Return the share of delivered effort going to new value vs. failure demand vs. maintenance.
8. `get_defect_trend`: Return failure-demand items created per time bucket with a slope indicator.
9. `get_stage_times`: Return per-stage median/p85 time for completed items.
10. `get_value_curve`: Return cumulative value delivered (actual vs. WSJF-ideal) and value efficiency.
11. `get_coaching_insights`: Return opinionated coaching recommendations for sprint planning, retro priorities, and WIP congestion.
