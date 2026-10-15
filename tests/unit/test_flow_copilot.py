import os
import sys
import pytest
import tempfile
import csv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from flow_copilot import (
    DataStore,
    compute_summary,
    compute_wip_aging,
    compute_blockers,
    compute_dependencies,
    compute_sprints,
    compute_outcomes,
    compute_coaching_insights,
)


@pytest.fixture
def temp_jira_data():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write flow_analytics_export.csv
        with open(
            os.path.join(tmpdir, "flow_analytics_export.csv"), "w", newline="", encoding="utf-8"
        ) as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "Issue Key",
                    "Summary",
                    "Issue Type",
                    "Created Date",
                    "Updated Date",
                    "Current Status",
                    "Implement",
                    "Done",
                ]
            )
            writer.writerow(
                [
                    "CI-1",
                    "Active Item",
                    "Story",
                    "2026-06-01 10:00:00",
                    "2026-06-05 10:00:00",
                    "Implement",
                    "2026-06-02 12:00:00",
                    "",
                ]
            )
            writer.writerow(
                [
                    "CI-2",
                    "Completed Item",
                    "Story",
                    "2026-06-01 10:00:00",
                    "2026-06-05 10:00:00",
                    "Done",
                    "2026-06-02 10:00:00",
                    "2026-06-04 10:00:00",
                ]
            )
            writer.writerow(
                [
                    "CI-3",
                    "Epic Blocker",
                    "Epic",
                    "2026-06-01 10:00:00",
                    "2026-06-05 10:00:00",
                    "Implement",
                    "2026-06-02 10:00:00",
                    "",
                ]
            )

        # Write issue_metadata.csv
        with open(
            os.path.join(tmpdir, "issue_metadata.csv"), "w", newline="", encoding="utf-8"
        ) as f:
            writer = csv.writer(f)
            writer.writerow(
                ["Issue Key", "Labels", "Story Points", "Resolution", "Epic Link", "Flagged"]
            )
            writer.writerow(["CI-1", "dev,ui", "3", "", "CI-3", "No"])
            writer.writerow(["CI-2", "dev", "5", "Done", "CI-3", "No"])
            writer.writerow(["CI-3", "", "", "", "", "Yes"])

        # Write sprint_data.csv
        with open(os.path.join(tmpdir, "sprint_data.csv"), "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                ["Issue Key", "Sprint ID", "Sprint Name", "Sprint State", "Start Date", "End Date"]
            )
            writer.writerow(
                ["CI-2", "1", "Sprint 1", "closed", "2026-06-01 00:00:00", "2026-06-14 00:00:00"]
            )

        # Write issue_links.csv
        with open(os.path.join(tmpdir, "issue_links.csv"), "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Source Issue Key", "Link Type Name", "Direction", "Target Issue Key"])
            writer.writerow(["CI-1", "Blocks", "Outward", "CI-2"])

        # Write flag_history.csv
        with open(os.path.join(tmpdir, "flag_history.csv"), "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Issue Key", "Date", "Action", "Comment", "Reason"])
            writer.writerow(
                [
                    "CI-1",
                    "2026-06-03 10:00:00",
                    "Flagged",
                    "Blocked by db vpn",
                    "Environment / Infrastructure",
                ]
            )
            writer.writerow(["CI-1", "2026-06-04 10:00:00", "Unflagged", "", ""])

        # Write issue_value_analysis.csv
        with open(
            os.path.join(tmpdir, "issue_value_analysis.csv"), "w", newline="", encoding="utf-8"
        ) as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "Issue Key",
                    "Issue Type",
                    "Summary",
                    "Taxonomy Level",
                    "Prescriptive Verbs",
                    "Suggested Outcome Framing",
                    "Rationale",
                ]
            )
            writer.writerow(
                [
                    "CI-3",
                    "Epic",
                    "Epic Blocker",
                    "Outcome",
                    "Increase, Improve",
                    "Increase throughput by fixing bottlenecks",
                    "High business alignment",
                ]
            )

        yield tmpdir


def test_copilot_data_loading(temp_jira_data):
    store = DataStore(temp_jira_data)
    assert len(store.issues) == 3
    assert store.issues[0]["key"] == "CI-1"
    assert store.issues[0]["estimation"] == 3.0
    assert "dev" in store.issues[0]["labels"]
    assert store.issues[1]["transitions"]["Done"] is not None


def test_copilot_metrics(temp_jira_data):
    store = DataStore(temp_jira_data)

    # Summary
    summary = compute_summary(store)
    assert summary["total_issues"] == 3
    assert summary["active_wip"] == 2
    assert summary["completed"] == 1
    assert summary["p50_cycle_time_days"] == 2.0

    # WIP Aging
    wip = compute_wip_aging(store)
    assert len(wip) == 2
    assert wip[0]["key"] in ["CI-1", "CI-3"]

    # Blockers
    blockers = compute_blockers(store)
    assert len(blockers) == 1
    assert blockers[0]["key"] == "CI-1"
    assert blockers[0]["total_blocked_days"] == 1.0

    # Dependencies
    deps = compute_dependencies(store)
    assert "CI-1" in deps["blocking"]
    assert deps["blocking"]["CI-1"] == ["CI-2"]

    # Sprints
    sprints = compute_sprints(store)
    assert len(sprints) == 1
    assert sprints[0]["id"] == "1"
    assert sprints[0]["completed_count"] == 1

    # Outcomes
    outcomes = compute_outcomes(store)
    assert outcomes["distribution"]["Outcome"] == 1
    assert len(outcomes["epics_framing"]) == 1
    assert outcomes["epics_framing"][0]["key"] == "CI-3"

    # Coaching Insights
    insights = compute_coaching_insights(store)
    assert insights["retrospective"]["top_blocker_category"] == "Infra: Access / Permissions"
    assert insights["outcome_alignment"]["feature_factory_risk"] is False
    assert "Infra: Access / Permissions" in insights["retrospective"]["advice"]
