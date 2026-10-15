import os
import sys
import pytest

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
def sample_data_store():
    # Use the generated sample data folder
    sample_data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../sample_data"))
    assert os.path.exists(sample_data_dir), (
        "sample_data directory does not exist! Run generate_sample_data.py first."
    )
    return DataStore(sample_data_dir)


def test_sample_data_loading(sample_data_store):
    store = sample_data_store
    # Check that it loads stories, bugs, epics
    assert len(store.issues) > 0

    # Verify epic fields
    epic1 = next(i for i in store.issues if i["key"] == "EPIC-1")
    assert epic1["type"] == "Epic"
    assert "EPIC-1" in epic1["summary"] or "Improve coach capability" in epic1["summary"]

    # Verify some stories exist
    stories = [i for i in store.issues if i["type"] in ("Story", "Bug")]
    assert len(stories) > 0


def test_summary_metrics(sample_data_store):
    store = sample_data_store
    summary = compute_summary(store)

    # Check general calculations
    assert summary["completed"] >= 0
    assert summary["active_wip"] > 0

    # Verify p50 and p85 cycle times (days)
    assert summary["p50_cycle_time_days"] >= 0
    assert summary["p85_cycle_time_days"] >= summary["p50_cycle_time_days"]


def test_wip_aging(sample_data_store):
    store = sample_data_store
    wip_items = compute_wip_aging(store)

    # Active WIP issues should be present
    assert len(wip_items) > 0

    # Check that age is tracked
    for item in wip_items:
        assert item["age_days"] >= 0.0


def test_blockers_and_penalties(sample_data_store):
    store = sample_data_store
    blockers = compute_blockers(store)

    # Blocker calculations
    assert len(blockers) > 0
    for b in blockers:
        assert b["total_blocked_days"] >= 0

    # Coaching insights retro checks blocker category
    insights = compute_coaching_insights(store)
    assert len(insights["retrospective"]["advice"]) > 0


def test_dependencies(sample_data_store):
    store = sample_data_store
    deps = compute_dependencies(store)

    # Blocking relationships exist
    assert len(deps["blocking"]) > 0


def test_sprints(sample_data_store):
    store = sample_data_store
    sprints_info = compute_sprints(store)

    # Sprints exist
    assert len(sprints_info) > 0
    for s in sprints_info:
        assert s["name"].startswith("Sprint")


def test_value_outcomes(sample_data_store):
    store = sample_data_store
    outcomes = compute_outcomes(store)

    # Verify the classification counts are present
    assert outcomes["distribution"]["Impact"] > 0
    assert outcomes["distribution"]["Outcome"] > 0
    assert outcomes["distribution"]["Output"] > 0
    assert outcomes["distribution"]["Activity"] > 0

    # Verify epic outcome framing is present
    assert len(outcomes["epics_framing"]) > 0


def test_scenarios_exist():
    sample_data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../sample_data"))
    for sc_folder in [
        "1_local_optimization_trap",
        "2_balanced_flow",
        "3_traditional_baseline",
        "4_balanced_ai_operating_model",
        "5_hyper_velocity_disaster",
        "6_hyper_velocity_quality_crash",
        "7_techdebt_underload",
        "8_balanced_ai_with_wip_limits",
        "9_safe_native_ai_transition",
        "10_sprint_carryover_and_predictability",
    ]:
        path = os.path.join(sample_data_dir, sc_folder)
        assert os.path.exists(path)
        assert os.path.exists(os.path.join(path, "flow_analytics_export.csv"))
        sprint_csv = os.path.join(path, "sprint_data.csv")
        assert os.path.exists(sprint_csv)
        assert os.path.getsize(sprint_csv) > 50  # Must be non-empty with sprint records


def test_scenario_6_has_regressions():
    sample_data_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../sample_data/6_hyper_velocity_quality_crash")
    )
    store = DataStore(sample_data_dir)
    # Check that there are regression bug items
    reg_bugs = [i for i in store.issues if "FLOW-REG-" in i["key"]]
    assert len(reg_bugs) > 0


def test_scenario_7_has_techdebt_and_lowpriority():
    sample_data_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../sample_data/7_techdebt_underload")
    )
    store = DataStore(sample_data_dir)
    # Check that there are injected starved items
    td_items = [i for i in store.issues if "FLOW-TD-" in i["key"]]
    assert len(td_items) > 0
    # Injected filler carries the disambiguated filler-* labels and Maintenance class
    all_labels = [lbl for i in td_items for lbl in i.get("labels", [])]
    assert any("filler-techdebt" in l for l in all_labels)
    assert any("filler-lowpriority" in l for l in all_labels)
    assert all(i.get("work_class") == "Maintenance" for i in td_items)


def test_work_class_inference_and_columns():
    from flow_copilot import infer_work_class

    # Explicit columns load from the simulator
    store = DataStore(
        os.path.abspath(
            os.path.join(
                os.path.dirname(__file__), "../../sample_data/6_hyper_velocity_quality_crash"
            )
        )
    )
    classes = {i.get("work_class") for i in store.issues if i["type"] != "Epic"}
    assert "Value" in classes
    assert "Failure Demand" in classes  # injected regressions
    # Inference fallback for real Jira exports without a Work Class column
    assert infer_work_class("Bug", []) == "Failure Demand"
    assert infer_work_class("Story", ["regression"]) == "Failure Demand"
    assert infer_work_class("Story", ["filler-lowpriority"]) == "Maintenance"
    assert infer_work_class("Story", ["capex"]) == "Value"


def test_innovation_rate_and_failure_demand():
    from flow_copilot import compute_innovation_rate

    base = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../sample_data"))
    # Quality-crash scenario must show failure demand eating into innovation rate
    crash = compute_innovation_rate(DataStore(os.path.join(base, "6_hyper_velocity_quality_crash")))
    assert crash["failure_demand_pct"] > 0
    assert crash["innovation_rate_pct"] < 100
    # Techdebt-underload must be dominated by maintenance/filler
    starve = compute_innovation_rate(DataStore(os.path.join(base, "7_techdebt_underload")))
    assert starve["maintenance_pct"] > 50
    # A healthy scenario is (near) all value
    healthy = compute_innovation_rate(
        DataStore(os.path.join(base, "8_balanced_ai_with_wip_limits"))
    )
    assert healthy["innovation_rate_pct"] > 95


def test_defect_trend_and_value_curve():
    from flow_copilot import compute_defect_trend, compute_value_curve, compute_stage_times

    base = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../sample_data"))
    crash = DataStore(os.path.join(base, "6_hyper_velocity_quality_crash"))
    trend = compute_defect_trend(crash)
    assert trend["total_defects"] > 0
    # Value curve available when Cost of Delay is present
    vc = compute_value_curve(crash)
    assert vc["available"] is True
    assert vc["value_efficiency_pct"] > 0
    # Starvation scenario sequences low-value filler ahead of waiting value -> low efficiency
    starve_vc = compute_value_curve(DataStore(os.path.join(base, "7_techdebt_underload")))
    assert starve_vc["value_efficiency_pct"] < 50
    # Per-stage breakdown returns active stages with positive medians
    stages = compute_stage_times(crash)
    assert any(s["stage"] == "Code Review" for s in stages)


def test_value_curve_cost_of_delay_proxy_cascade():
    """The value curve must degrade gracefully for real Jira exports: Cost of Delay,
    then Priority field, then FIFO arrival order."""
    from flow_copilot import compute_value_curve

    base = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../sample_data"))
    store = DataStore(os.path.join(base, "6_hyper_velocity_quality_crash"))

    # 1. Explicit Cost of Delay present -> cost_of_delay mode
    assert compute_value_curve(store)["mode"] == "cost_of_delay"

    # 2. Strip CoD, supply Priority -> priority mode
    prios = ["Highest", "High", "Medium", "Low", "Lowest"]
    for idx, i in enumerate(store.issues):
        i["cost_of_delay"] = None
        i["priority_field"] = prios[idx % len(prios)]
    pri = compute_value_curve(store)
    assert pri["mode"] == "priority"
    assert pri["available"] is True

    # 3. Strip everything -> FIFO fallback
    for i in store.issues:
        i["priority_field"] = ""
        i["rank"] = ""
    fifo = compute_value_curve(store)
    assert fifo["mode"] == "fifo"
    assert 0 <= fifo["value_efficiency_pct"] <= 100
