---
name: jira-value-ops
description: Enrich exported Jira datasets with value and outcome taxonomy classifications and epic framing suggestions in-session. Use when the user requests a value/outcome analysis or outcome coaching on their exported Jira issues.
metadata:
  version: 1.1.0
---

# Jira Value Ops

## Outcome
Enrich a Jira export folder with value/outcome taxonomy classifications and outcome framing suggestions, writing them into `issue_value_analysis.csv` so they can be loaded by the Value/Outcome Coaching Dashboard.

## Prerequisites
- A Jira export directory containing:
  - `flow_analytics_export.csv` (contains "Issue Key", "Summary", "Issue Type", "Current Status")
  - `issue_metadata.csv` (contains "Issue Key", "Labels")

## Process

1. **Locate and Ingest Data**:
   - Locate the target directory containing the CSV files.
   - Read the contents of `flow_analytics_export.csv` and `issue_metadata.csv`.

2. **Classify Epics via LLM (Parallel Batch Agents)**:
   - Extract all Epics from `flow_analytics_export.csv` into `epics_raw.json`.
   - Split into batches of ~300 epics each (e.g. 8 batches for ~2,400 epics). Save as `epics_batch_1.json` … `epics_batch_N.json`.
   - Spawn one background Agent per batch (`run_in_background: true`, model: haiku) with the taxonomy prompt below. Each agent returns a JSON array: `[{"key": "PROJ-123", "level": "Output", "framing": "", "rationale": "..."}]`.
   - Wait for all task notifications. Extract results from the notification `<result>` tag (they are inline — output files on disk will be 0 bytes). Save each batch to `batch_results_N.json`.

3. **Apply Post-Processing Rules** (correct systematic Haiku blind spots):
   - **Quarterly bucket override**: Any epic whose summary matches `^(FY\s*'?\d{2,4}\s*Q\d|Y\s*'?\d{2,4}\s*Q\d)` → force to **Activity**, regardless of what Haiku classified. Haiku picks up the deliverable inside the time-box and says Output; the quarterly container always wins.
   - **Impact/Outcome check**: "Increase audience X%" or "retain N PVs" are Impact (business metric), not Outcome (user capability). If the subject of improvement is an org-level metric, prefer Impact over Outcome.

4. **Classify Non-Epics via Rule-Based Classifier**:
   - Run `offline_analysis_value.py` which loads LLM batch results for Epics and applies the keyword-based `classify()` function for all other issue types (Stories, Tasks, Bugs, Sub-tasks).

5. **Output `issue_value_analysis.csv`**:
   - Written by `offline_analysis_value.py` to the export directory.
   - Columns: `Issue Key, Issue Type, Summary, Taxonomy Level, Prescriptive Verbs, Suggested Outcome Framing, Rationale`

6. **Load into Dashboard**:
   - Run `npm start` and open `value_dashboard.html` or `index.html` to load the enriched folder.

## LLM vs Rule-Based Taxonomy Notes

- **LLM semantic classification (Haiku) outperforms keyword matching for Epics**. Rule-based produces false-positives like "Revenue Report ingested via CSV" → Impact (contains "revenue").
- **Haiku quality: ~70% agreement with Sonnet** on unseen epics. The two systematic errors are both fixable with post-processing rules (quarterly bucket + Impact/Outcome boundary).
- **Non-Epic issues** (Stories, Tasks, Bugs) don't warrant LLM cost: Bug → Activity always; Story/Task defaults to Activity unless strong Output signals. Rule-based is sufficient.

## Batch Classification Prompt (for background agents)

```
Classify each epic below on the Input→Activity→Output→Outcome→Impact taxonomy.

Taxonomy:
- Impact: explicit business result — BOTH improvement verb + business metric. VERY RARE.
- Outcome: new USER CAPABILITY ("users can X"). Requires user capability change, not just technical work.
- Output: deliverable artifact, feature, system, migration. MOST epics are Outputs.
- Activity: work/process — QA, DevOps, maintenance, discovery/spike/POC, data ingestion, support, training, refactoring, quarterly buckets.
- Input: resource allocation. Very rare.

Critical rules:
1. Data ingestion/ETL/pipeline → Activity
2. Technical retention ≠ customer retention
3. Technical enablement ≠ Outcome (requires USER capability change)
4. Quarterly buckets (FY##Q#, Y##Q#) → Activity
5. Named initiatives/codenames → Output
6. Short/ambiguous names → Output
7. Discovery/Spike/POC → Activity
8. Platform/system migration → Output; data/user migration → Activity

Return a raw JSON array (no markdown fences), one object per epic:
{"key": "PROJ-123", "level": "Output", "framing": "", "rationale": "one sentence"}

Epics:
[paste epics_batch_N.json content here]
```
