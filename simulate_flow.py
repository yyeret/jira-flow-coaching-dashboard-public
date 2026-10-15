#!/usr/bin/env python3
import os
import json
import csv
import re
import random
from datetime import datetime, timedelta


def load_config(filepath):
    if not os.path.exists(filepath):
        print(f"Warning: config file {filepath} not found. Using default parameters.")
        return get_default_config()
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    m = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception as e:
            print(f"Error parsing JSON from config: {e}. Using default parameters.")
            return get_default_config()
    else:
        print("Warning: JSON block not found in config. Using default parameters.")
        return get_default_config()


def get_default_config():
    return {
        "simulation_days": 90,
        "sprint_length_days": 14,
        "enable_wip_limits": False,
        "epic_min_stories": 3,
        "epic_max_stories": 20,
        "workflow_order": [
            "Open",
            "To Do",
            "Specify/Plan",
            "Ready to Implement",
            "Next",
            "Implement",
            "Code Review",
            "Ready for Testing",
            "test and fix",
            "Ready for release",
            "Monitor/Adapt/Learn",
            "Done",
        ],
        "wip_limits": {
            "Specify/Plan": 3,
            "Ready to Implement": 10,
            "Next": 3,
            "Implement": 4,
            "Code Review": 2,
            "Ready for Testing": 5,
            "test and fix": 2,
            "Ready for release": 5,
            "Monitor/Adapt/Learn": 3,
        },
        "base_durations": {
            "Specify/Plan": 0.5,
            "Ready to Implement": 0.0,
            "Next": 0.0,
            "Implement": 6.0,
            "Code Review": 2.0,
            "Ready for Testing": 0.5,
            "test and fix": 3.0,
            "Ready for release": 1.0,
            "Monitor/Adapt/Learn": 2.0,
        },
        "stage_multipliers": {
            "Specify/Plan": {"human": 1.0, "ai-coding-assist": 1.0, "agentic-ai": 1.0},
            "Ready to Implement": {"human": 1.0, "ai-coding-assist": 1.0, "agentic-ai": 1.0},
            "Next": {"human": 1.0, "ai-coding-assist": 1.0, "agentic-ai": 1.0},
            "Implement": {"human": 1.0, "ai-coding-assist": 0.33, "agentic-ai": 0.1},
            "Code Review": {"human": 1.0, "ai-coding-assist": 1.0, "agentic-ai": 1.0},
            "Ready for Testing": {"human": 1.0, "ai-coding-assist": 1.0, "agentic-ai": 1.0},
            "test and fix": {"human": 1.0, "ai-coding-assist": 0.5, "agentic-ai": 0.2},
            "Ready for release": {"human": 1.0, "ai-coding-assist": 1.0, "agentic-ai": 1.0},
            "Monitor/Adapt/Learn": {"human": 1.0, "ai-coding-assist": 1.0, "agentic-ai": 1.0},
        },
        "capacities": {
            "Specify/Plan": 2,
            "Implement": 4,
            "Code Review": 2,
            "test and fix": 2,
            "Monitor/Adapt/Learn": 2,
        },
    }


# ─── VALUE / WORK-CLASS MODEL ────────────────────────────────────────────────
# Work Class is the shared primitive behind the EBM-style metrics. Every item is
# one of three classes, and each carries a Cost of Delay (CoD) so we can reason
# about value (WSJF = CoD / size) rather than just flow.
WORK_CLASS_VALUE = "Value"  # new product capability (the work that should lead)
WORK_CLASS_FAILURE = "Failure Demand"  # rework / defects caused by our own quality misses
WORK_CLASS_MAINTENANCE = "Maintenance"  # keep-the-lights-on filler / low-priority techdebt

# Priority tiers drive preemption: lower number is pulled/worked first. Failure
# demand expedites ahead of value; filler only runs when nothing better is ready.
PRIORITY_BY_CLASS = {
    WORK_CLASS_FAILURE: 0,
    WORK_CLASS_VALUE: 1,
    WORK_CLASS_MAINTENANCE: 2,
}


# Cost of Delay tiers map onto the existing value taxonomy so the Outcome/Activity
# chart finally differentiates. High-CoD value work reads as Outcome/Impact; filler
# and rework read as low-value.
def assign_cost_of_delay(work_class):
    """Return (cost_of_delay, taxonomy_level) for a given work class."""
    if work_class == WORK_CLASS_FAILURE:
        # Defects expedite: high urgency, but they destroy value rather than create it.
        return random.choice([60, 75, 90]), "Failure Demand"
    if work_class == WORK_CLASS_MAINTENANCE:
        # Filler / low-priority: always cheap to delay.
        return random.choice([3, 5, 8, 10]), "Activity"
    # Value features get a real spread so sequencing (WSJF) actually matters.
    roll = random.random()
    if roll < 0.2:
        return random.choice([70, 85, 100]), "Impact"  # high CoD, top of the queue
    if roll < 0.5:
        return random.choice([35, 45, 55]), "Outcome"  # solid value
    if roll < 0.8:
        return random.choice([18, 22, 28]), "Output"  # modest value
    return random.choice([5, 8, 12]), "Activity"  # low CoD value


class SimulatedIssue:
    def __init__(
        self,
        key,
        summary,
        issue_type,
        epic,
        sp,
        label_type,
        specific_labels=None,
        work_class=WORK_CLASS_VALUE,
    ):
        self.key = key
        self.summary = summary
        self.issue_type = issue_type
        self.epic = epic
        self.sp = sp
        self.label_type = label_type  # human, ai-coding-assist, agentic-ai
        self.work_class = work_class

        # Cost of Delay + WSJF (CoD / size) + the taxonomy tier it implies.
        self.cost_of_delay, self.taxonomy_level = assign_cost_of_delay(work_class)
        self.wsjf = self.cost_of_delay / float(self.sp if self.sp else 1)
        self.priority = PRIORITY_BY_CLASS.get(work_class, 1)

        # Labels string. We tag the work class explicitly so it is cleanly sliceable
        # in the dashboard instead of being conflated with random domain labels.
        if specific_labels is not None:
            other_labels = list(specific_labels)
        else:
            other_labels = random.choice(
                [["capex"], ["revenue"], ["techdebt"], ["riskreduction"], ["fixeddate"], []]
            )
            if self.label_type != "human":
                other_labels.append(self.label_type)
        self.labels = ", ".join(other_labels)

        self.current_stage_idx = 0
        self.remaining_days = 0.0
        self.created_day = 0.0  # day the item entered the system (set on injection)
        self.transitions = {}  # stage_name -> day_float

        # Blockers log
        self.flags = []  # dicts: {date_day, action, reason, comment}
        self.is_flagged = False
        self.flagged_day = None
        self.flag_reason = None

        # Sprint tracking
        self.sprints_involved = set()  # sprint_ids
        self.mid_sprint_sprints = set()  # sprint_ids

    def enter_stage(self, stage_idx, day, stage_name, duration):
        self.current_stage_idx = stage_idx
        self.remaining_days = float(duration)
        self.transitions[stage_name] = day

    def flag(self, day, reason, comment):
        if not self.is_flagged:
            self.is_flagged = True
            self.flagged_day = day
            self.flag_reason = reason
            self.flags.append(
                {"day": day, "action": "Flagged", "reason": reason, "comment": comment}
            )

    def unflag(self, day):
        if self.is_flagged:
            self.is_flagged = False
            self.flags.append(
                {"day": day, "action": "Unflagged", "reason": self.flag_reason, "comment": ""}
            )
            self.flagged_day = None
            self.flag_reason = None


def run_simulation(config, scenario_opts):
    # Setup random seed for reproducibility
    random.seed(42)

    simulation_days = scenario_opts.get("simulation_days", config["simulation_days"])
    sprint_length_days = config["sprint_length_days"]

    enable_wip_limits = scenario_opts.get("wip_limits", config["enable_wip_limits"])
    workflow_order = config["workflow_order"]
    wip_limits = dict(config["wip_limits"])
    base_durations = dict(config["base_durations"])
    stage_multipliers = {k: dict(v) for k, v in config["stage_multipliers"].items()}
    capacities = dict(config["capacities"])

    # Apply scenario specific overrides
    all_human = scenario_opts.get("all_human", False)
    ai_review = scenario_opts.get("ai_review", False)
    ai_test = scenario_opts.get("ai_test", False)
    hyper_velocity = scenario_opts.get("hyper_velocity", False)
    quality_crash = scenario_opts.get("quality_crash", False)
    upstream_starvation = scenario_opts.get("upstream_starvation", False)

    if all_human:
        # Override all multipliers to 1.0 (traditional baseline)
        for stage in stage_multipliers:
            for l_type in stage_multipliers[stage]:
                stage_multipliers[stage][l_type] = 1.0

    if ai_review:
        # Code Review is AI-assisted (3x speedup for assist, 5x for agentic)
        stage_multipliers["Code Review"]["ai-coding-assist"] = 0.33
        stage_multipliers["Code Review"]["agentic-ai"] = 0.2
        capacities["Code Review"] = 4  # increased capacity due to AI assistance

    if ai_test:
        # test and fix is AI-assisted (4x speedup for assist, 10x for agentic)
        stage_multipliers["test and fix"]["ai-coding-assist"] = 0.25
        stage_multipliers["test and fix"]["agentic-ai"] = 0.1
        capacities["test and fix"] = 4  # increased capacity

    if hyper_velocity:
        # Implement is hyper-fast (20x speedup for agentic!)
        stage_multipliers["Implement"]["ai-coding-assist"] = 0.15
        stage_multipliers["Implement"]["agentic-ai"] = 0.05

    if quality_crash:
        # Testing is rushed / forced to work at 5x speed
        stage_multipliers["test and fix"]["human"] = 0.2
        stage_multipliers["test and fix"]["ai-coding-assist"] = 0.1
        stage_multipliers["test and fix"]["agentic-ai"] = 0.04

    # Backlog feed parameters
    feed_interval = 2.0
    feed_count = 3
    if hyper_velocity or quality_crash:
        # Double the feed rate to represent the deluge of backlog tickets
        feed_interval = 2.0
        feed_count = 4
    if upstream_starvation:
        # Slower specification rate for high value features
        feed_interval = 10.0
        feed_count = 1

    # Calculate sprint time ranges
    sprints = []
    start_offset = 5.0
    for i in range(1, 10):
        s_start = start_offset + (i - 1) * sprint_length_days
        s_end = s_start + sprint_length_days
        state = "closed"
        if s_start <= simulation_days < s_end:
            state = "active"
        elif s_start > simulation_days:
            state = "future"
        sprints.append(
            {"id": str(i), "name": f"Sprint {i}", "state": state, "start": s_start, "end": s_end}
        )

    safe_native_ai = scenario_opts.get("safe_native_ai", False)

    if safe_native_ai:
        epics_raw = [
            {
                "key": "EPIC-1",
                "summary": "AI-Powered Customer Support Automation",
                "type": "Epic",
                "taxonomy": "Outcome",
                "labels": "revenue",
            },
            {
                "key": "EPIC-2",
                "summary": "GenAI Marketing Content Generation Platform",
                "type": "Epic",
                "taxonomy": "Output",
                "labels": "capex",
            },
            {
                "key": "EPIC-3",
                "summary": "Predictive Maintenance AI Models for Manufacturing",
                "type": "Epic",
                "taxonomy": "Impact",
                "labels": "revenue",
            },
            {
                "key": "EPIC-4",
                "summary": "Upgrade GPU Cluster Infrastructure",
                "type": "Epic",
                "taxonomy": "Activity",
                "labels": "techdebt",
            },
            {
                "key": "EPIC-5",
                "summary": "AI-Driven Fraud Detection Engine",
                "type": "Epic",
                "taxonomy": "Outcome",
                "labels": "riskreduction",
            },
        ]

        feature_templates = [
            # For EPIC-1 (Outcome)
            ("Natural Language chatbot for level-1 triage", "EPIC-1"),
            ("Sentiment analysis integration for ticket escalation", "EPIC-1"),
            ("Automated knowledge base article generator", "EPIC-1"),
            ("Voice-to-text translation service for call center", "EPIC-1"),
            # For EPIC-2 (Output)
            ("LLM prompt management UI template", "EPIC-2"),
            ("Image generation pipeline integration", "EPIC-2"),
            ("Bulk copy generation API endpoints", "EPIC-2"),
            ("A/B test variation generator", "EPIC-2"),
            # For EPIC-3 (Impact)
            ("IoT sensor data ingestion stream", "EPIC-3"),
            ("Anomaly detection model training pipeline", "EPIC-3"),
            ("Predictive failure alert dashboard", "EPIC-3"),
            ("Maintenance scheduling optimization algorithm", "EPIC-3"),
            # For EPIC-4 (Activity)
            ("Procure and rack new Nvidia H100 servers", "EPIC-4"),
            ("Configure Kubernetes GPU node pools", "EPIC-4"),
            ("Update PyTorch distributed training libraries", "EPIC-4"),
            ("Network topology reconfiguration for high bandwidth", "EPIC-4"),
            # For EPIC-5 (Outcome)
            ("Real-time transaction scoring microservice", "EPIC-5"),
            ("Graph neural network for entity resolution", "EPIC-5"),
            ("Fraud analyst human-in-the-loop review queue", "EPIC-5"),
            ("Automated account freezing protocol", "EPIC-5"),
        ]

        epics = []
        for idx, e in enumerate(epics_raw):
            e_copied = dict(e)
            epics.append(e_copied)

        for idx, (summary, parent_key) in enumerate(feature_templates):
            parent_epic = next((e for e in epics_raw if e["key"] == parent_key), None)
            epics.append(
                {
                    "key": f"FEAT-{idx + 1}",
                    "summary": summary,
                    "type": "Feature",
                    "taxonomy": parent_epic["taxonomy"] if parent_epic else "Output",
                    "labels": parent_epic["labels"] if parent_epic else "capex",
                    "parent_epic": parent_key,
                }
            )

        # Generate stories for each Feature
        backlog = []
        issue_counter = 1

        # Build stories per feature
        temp_backlog = []
        for epic_idx, epic_obj in enumerate(epics):
            # Only Features have child stories directly under them in this model!
            if epic_obj["type"] != "Feature":
                continue

            # Each feature gets a random number of stories between 4 and 12 (average 8)
            size = random.randint(4, 12)

            for _ in range(size):
                key = f"FLOW-{issue_counter}"
                issue_counter += 1

                issue_type = "Story" if random.random() < 0.8 else "Bug"
                sp = (
                    random.choice([1, 2, 3, 5, 8, 13])
                    if issue_type == "Story"
                    else random.choice([1, 2, 3])
                )

                # Determine label type based on epic index to keep it diverse
                label_type = random.choice(["human", "ai-coding-assist", "agentic-ai"])

                if label_type == "agentic-ai":
                    summary = (
                        f"Agentic search and tool loop for {epic_obj['key']} slice {issue_counter}"
                    )
                elif label_type == "ai-coding-assist":
                    summary = f"Refactor templates for {epic_obj['key']} using coding assist"
                else:
                    summary = (
                        f"Human designer review and documentation for {epic_obj['key']} layout"
                    )

                # Priority weight sorting to generally group them by feature sequence
                priority_weight = epic_idx * 5.0 + random.uniform(-6.0, 6.0)

                temp_backlog.append(
                    {
                        "issue": SimulatedIssue(
                            key, summary, issue_type, epic_obj["key"], sp, label_type
                        ),
                        "priority_weight": priority_weight,
                    }
                )

        # Sort backlog by priority weight to align their prioritization while retaining natural overlap
        temp_backlog.sort(key=lambda item: item["priority_weight"])

        # Re-key issues to match their final sorted backlog sequence
        for final_idx, item in enumerate(temp_backlog):
            issue = item["issue"]
            issue.key = f"FLOW-{final_idx + 1}"
            backlog.append(issue)

    else:
        # Define Epics
        epics = [
            {
                "key": "EPIC-1",
                "summary": "Improve coach capability to guide teams by visualizing flow metrics",
                "type": "Epic",
                "taxonomy": "Outcome",
                "labels": "revenue, agentic-ai",
            },
            {
                "key": "EPIC-2",
                "summary": "Build Cumulative Flow Diagram CFD chart component",
                "type": "Epic",
                "taxonomy": "Output",
                "labels": "capex",
            },
            {
                "key": "EPIC-3",
                "summary": "Implement Sprint Comet Chart with Tetris layout",
                "type": "Epic",
                "taxonomy": "Output",
                "labels": "capex, ai-coding-assist",
            },
            {
                "key": "EPIC-4",
                "summary": "FY26Q2 | Upgrade system dependencies and dev environment",
                "type": "Epic",
                "taxonomy": "Activity",
                "labels": "techdebt",
            },
            {
                "key": "EPIC-5",
                "summary": "Increase NPS satisfaction of coaches by 20% through dashboard insights",
                "type": "Epic",
                "taxonomy": "Impact",
                "labels": "riskreduction",
            },
        ]

        # Calculate required backlog size dynamically to prevent running dry before simulation ends
        required_backlog = int((simulation_days / feed_interval) * feed_count) + 15

        # Retrieve min and max stories per epic from config
        epic_min = config.get("epic_min_stories", 3)
        epic_max = config.get("epic_max_stories", 20)

        # Additional templates for dynamically generated epics
        extra_epics_templates = [
            ("Integrate slack notification for flow metrics alerts", "Output", "capex"),
            ("Reduce average build and deployment pipeline time by 50%", "Outcome", "techdebt"),
            (
                "Implement flow efficiency analytics in the dashboard",
                "Output",
                "capex, ai-coding-assist",
            ),
            ("Scale data ingestion to support multi-project JQL queries", "Outcome", "revenue"),
            (
                "Improve user onboarding experience for first-time coaches",
                "Impact",
                "riskreduction",
            ),
            ("Audit security permissions and restrict API token scopes", "Activity", "techdebt"),
            ("Add customizable widgets to the executive dashboard view", "Output", "capex"),
            (
                "Establish automated regression testing for chart rendering",
                "Outcome",
                "techdebt, ai-coding-assist",
            ),
            ("Reduce database query latency under heavy concurrent load", "Outcome", "techdebt"),
            ("Design and publish coaching playbook for Flow methodology", "Impact", "revenue"),
            ("Upgrade frontend framework dependencies and libraries", "Activity", "techdebt"),
            (
                "Implement role-based access control for enterprise clients",
                "Output",
                "capex, agentic-ai",
            ),
        ]

        # Assign sizes for standard epics and generate more epics if needed to cover required_backlog
        epic_sizes = []
        for _ in range(len(epics)):
            epic_sizes.append(random.randint(epic_min, epic_max))

        current_epic_idx = len(epics) + 1
        while sum(epic_sizes) < required_backlog:
            size = random.randint(epic_min, epic_max)
            epic_sizes.append(size)

            template_idx = (current_epic_idx - 6) % len(extra_epics_templates)
            summary, taxonomy, labels = extra_epics_templates[template_idx]
            loop_num = (current_epic_idx - 6) // len(extra_epics_templates)
            suffix = f" (Phase {loop_num + 2})" if loop_num > 0 else ""

            epics.append(
                {
                    "key": f"EPIC-{current_epic_idx}",
                    "summary": f"{summary}{suffix}",
                    "type": "Epic",
                    "taxonomy": taxonomy,
                    "labels": labels,
                }
            )
            current_epic_idx += 1

        # Build a label pool matching the generated backlog size
        total_stories_to_generate = sum(epic_sizes)
        label_pool = []
        pool_patterns = ["human", "ai-coding-assist", "agentic-ai"]
        for idx in range(total_stories_to_generate):
            label_pool.append(pool_patterns[idx % len(pool_patterns)])
        random.shuffle(label_pool)

        # Generate stories for each epic
        temp_backlog = []
        label_pool_idx = 0
        issue_counter = 1

        for epic_idx, epic_obj in enumerate(epics):
            epic_key = epic_obj["key"]
            size = epic_sizes[epic_idx]
            for _ in range(size):
                key = f"FLOW-{issue_counter}"
                issue_counter += 1

                issue_type = "Story" if random.random() < 0.8 else "Bug"
                sp = (
                    random.choice([1, 2, 3, 5, 8, 13])
                    if issue_type == "Story"
                    else random.choice([1, 2, 3])
                )
                label_type = label_pool[label_pool_idx]
                label_pool_idx += 1

                if label_type == "agentic-ai":
                    summary = f"Agentic search and tool loop for {epic_key} slice {issue_counter}"
                elif label_type == "ai-coding-assist":
                    summary = f"Refactor templates for {epic_key} using coding assist"
                else:
                    summary = f"Human designer review and documentation for {epic_key} layout"

                # Assign a sort priority with some jitter to generally group them but allow natural flow/overlap
                priority_weight = epic_idx * 3.0 + random.uniform(-5.0, 5.0)

                temp_backlog.append(
                    {
                        "issue": SimulatedIssue(key, summary, issue_type, epic_key, sp, label_type),
                        "priority_weight": priority_weight,
                    }
                )

        # Sort backlog by priority weight to align their prioritization while retaining natural overlap
        temp_backlog.sort(key=lambda item: item["priority_weight"])

        # Re-key issues to match their final sorted backlog sequence
        backlog = []
        for final_idx, item in enumerate(temp_backlog):
            issue = item["issue"]
            issue.key = f"FLOW-{final_idx + 1}"
            backlog.append(issue)

    # Initialize epic simulation parameters
    # Initialize epic simulation parameters
    epic_workflow = [
        "FUNNEL",
        "REVIEW",
        "ANALYZE",
        "READY",
        "DISCOVER",
        "DELIVER",
        "MEASURE/LEARN",
        "DONE",
    ]
    feat_workflow = [
        "FEATURE FUNNEL",
        "ANALYZING",
        "READY",
        "PI BACKLOG",
        "IMPLEMENTING",
        "READY FOR INTEGRATION/TESTING",
        "INTEGRATING / TESTING",
        "READY FOR RELEASE",
        "RELEASE & IMPROVE",
        "DONE",
    ]
    epic_workflow_default = [
        "FUNNEL",
        "ANALYZE",
        "READY",
        "PI PLANNING",
        "IMPLEMENT",
        "DEPLOY",
        "MEASURE/LEARN",
        "DONE",
    ]
    epic_durations_default = {
        "FUNNEL": 2.0,
        "ANALYZE": 4.0,
        "READY": 3.0,
        "PI PLANNING": 2.0,
        "IMPLEMENT": 2.0,
        "DEPLOY": 2.0,
        "MEASURE/LEARN": 5.0,
    }
    for idx, epic in enumerate(epics):
        if safe_native_ai:
            if epic["type"] == "Epic":
                # Epic starts are spaced out across the first 60 days
                epic["created_day"] = idx * 15.0
            else:
                # Features are initialized at -1, they enter FUNNEL dynamically when their parent Epic hits DELIVER
                epic["created_day"] = 9999.0
        else:
            epic["created_day"] = idx * 4.0
        epic["current_stage_idx"] = -1
        epic["current_stage"] = None
        epic["remaining_days"] = 0.0
        epic["transitions"] = {}

    # Queue maps for each stage
    stages = {state: [] for state in workflow_order}

    # Initialize simulation: all issues start in "Open" on day 0
    for issue in backlog:
        issue.enter_stage(0, 0.0, "Open", 0.0)
        stages["Open"].append(issue)

    # Simulation engine tick
    tick_rate = 0.1
    current_day = 0.0

    reg_bug_counter = 1
    starved_counter = 1

    # Simulation loop
    while current_day < simulation_days:
        # 0. Simulate Epic and Feature transitions
        if safe_native_ai:
            if current_day < 60.0:
                feat_durations = {
                    "FEATURE FUNNEL": 3.0,
                    "ANALYZING": 2.0,
                    "READY": 1.0,
                    "PI BACKLOG": 0.5,
                    "IMPLEMENTING": 0.0,
                    "READY FOR INTEGRATION/TESTING": 0.5,
                    "INTEGRATING / TESTING": 2.0,
                    "READY FOR RELEASE": 0.5,
                    "RELEASE & IMPROVE": 4.0,
                }
                epic_durations = {
                    "FUNNEL": 10.0,
                    "REVIEW": 4.0,
                    "ANALYZE": 6.0,
                    "READY": 3.0,
                    "DISCOVER": 2.0,
                    "DELIVER": 0.0,
                    "MEASURE/LEARN": 10.0,
                }
            elif current_day < 120.0:
                feat_durations = {
                    "FEATURE FUNNEL": 3.0,
                    "ANALYZING": 2.0,
                    "READY": 2.5,
                    "PI BACKLOG": 1.5,
                    "IMPLEMENTING": 0.0,
                    "READY FOR INTEGRATION/TESTING": 1.5,
                    "INTEGRATING / TESTING": 2.5,
                    "READY FOR RELEASE": 1.0,
                    "RELEASE & IMPROVE": 2.5,
                }
                epic_durations = {
                    "FUNNEL": 10.0,
                    "REVIEW": 4.0,
                    "ANALYZE": 6.0,
                    "READY": 3.0,
                    "DISCOVER": 2.0,
                    "DELIVER": 0.0,
                    "MEASURE/LEARN": 10.0,
                }
            else:
                feat_durations = {
                    "FEATURE FUNNEL": 1.2,
                    "ANALYZING": 0.8,
                    "READY": 1.0,
                    "PI BACKLOG": 0.5,
                    "IMPLEMENTING": 0.0,
                    "READY FOR INTEGRATION/TESTING": 0.2,
                    "INTEGRATING / TESTING": 1.0,
                    "READY FOR RELEASE": 0.2,
                    "RELEASE & IMPROVE": 1.0,
                }
                epic_durations = {
                    "FUNNEL": 4.0,
                    "REVIEW": 2.0,
                    "ANALYZE": 2.0,
                    "READY": 1.0,
                    "DISCOVER": 1.0,
                    "DELIVER": 0.0,
                    "MEASURE/LEARN": 5.0,
                }

            for item in epics:
                if item["type"] == "Epic":
                    # Entry
                    if item["current_stage_idx"] == -1 and current_day >= item["created_day"]:
                        item["current_stage_idx"] = 0
                        stage_name = epic_workflow[0]
                        item["current_stage"] = stage_name
                        item["transitions"][stage_name] = current_day
                        item["remaining_days"] = epic_durations.get(stage_name, 0.0)

                    # Active transitions
                    if item["current_stage_idx"] >= 0:
                        stage_name = epic_workflow[item["current_stage_idx"]]
                        if stage_name == "IMPLEMENT":
                            child_features = [
                                f
                                for f in epics
                                if f["type"] == "Feature" and f.get("parent_epic") == item["key"]
                            ]
                            all_features_done = True
                            for feat in child_features:
                                if feat.get("current_stage") != "DONE":
                                    all_features_done = False
                                    break
                            if child_features and all_features_done:
                                item["current_stage_idx"] += 1
                                next_stage = epic_workflow[item["current_stage_idx"]]
                                item["current_stage"] = next_stage
                                item["transitions"][next_stage] = current_day
                                item["remaining_days"] = epic_durations.get(next_stage, 0.0)
                        elif stage_name != "DONE":
                            item["remaining_days"] -= tick_rate
                            if item["remaining_days"] <= 0:
                                item["remaining_days"] = 0.0
                                item["current_stage_idx"] += 1
                                next_stage = epic_workflow[item["current_stage_idx"]]
                                item["current_stage"] = next_stage
                                item["transitions"][next_stage] = current_day

                                # Trigger child features to start FEATURE FUNNEL when parent Epic transitions to DELIVER
                                if next_stage == "DELIVER":
                                    child_features = [
                                        f
                                        for f in epics
                                        if f["type"] == "Feature"
                                        and f.get("parent_epic") == item["key"]
                                    ]
                                    for feat in child_features:
                                        feat["current_stage_idx"] = 0
                                        feat["current_stage"] = "FEATURE FUNNEL"
                                        feat["transitions"]["FEATURE FUNNEL"] = current_day
                                        feat["remaining_days"] = feat_durations.get(
                                            "FEATURE FUNNEL", 0.0
                                        )
                                        feat["created_day"] = current_day

                                item["remaining_days"] = epic_durations.get(next_stage, 0.0)

                elif item["type"] == "Feature":
                    if item["current_stage_idx"] >= 0:
                        stage_name = feat_workflow[item["current_stage_idx"]]
                        if stage_name == "IMPLEMENTING":
                            child_stories = [s for s in backlog if s.epic == item["key"]]
                            all_stories_done = True
                            for story in child_stories:
                                if workflow_order[story.current_stage_idx] != "Done":
                                    all_stories_done = False
                                    break
                            if child_stories and all_stories_done:
                                item["current_stage_idx"] += 1
                                next_stage = feat_workflow[item["current_stage_idx"]]
                                item["current_stage"] = next_stage
                                item["transitions"][next_stage] = current_day
                                item["remaining_days"] = feat_durations.get(next_stage, 0.0)
                        elif stage_name != "DONE":
                            item["remaining_days"] -= tick_rate
                            if item["remaining_days"] <= 0:
                                item["remaining_days"] = 0.0
                                item["current_stage_idx"] += 1
                                next_stage = feat_workflow[item["current_stage_idx"]]
                                item["current_stage"] = next_stage
                                item["transitions"][next_stage] = current_day
                                item["remaining_days"] = feat_durations.get(next_stage, 0.0)
        else:
            for epic in epics:
                if epic["current_stage_idx"] == -1 and current_day >= epic["created_day"]:
                    epic["current_stage_idx"] = 0
                    stage_name = epic_workflow_default[0]
                    epic["current_stage"] = stage_name
                    epic["transitions"][stage_name] = current_day
                    epic["remaining_days"] = epic_durations_default.get(stage_name, 0.0)

                if epic["current_stage_idx"] >= 0:
                    stage_name = epic_workflow_default[epic["current_stage_idx"]]
                    if stage_name == "IMPLEMENT":
                        epic_stories = [item for item in backlog if item.epic == epic["key"]]
                        all_done = True
                        for story in epic_stories:
                            if workflow_order[story.current_stage_idx] != "Done":
                                all_done = False
                                break
                        if all_done:
                            epic["current_stage_idx"] += 1
                            next_stage = epic_workflow_default[epic["current_stage_idx"]]
                            epic["current_stage"] = next_stage
                            epic["transitions"][next_stage] = current_day
                            epic["remaining_days"] = epic_durations_default.get(next_stage, 0.0)
                    elif stage_name != "DONE":
                        epic["remaining_days"] -= tick_rate
                        if epic["remaining_days"] <= 0:
                            epic["remaining_days"] = 0.0
                            epic["current_stage_idx"] += 1
                            next_stage = epic_workflow_default[epic["current_stage_idx"]]
                            epic["current_stage"] = next_stage
                            epic["transitions"][next_stage] = current_day
                            epic["remaining_days"] = epic_durations_default.get(next_stage, 0.0)

        # 1. Backlog feeding
        feed_interval_ticks = int(feed_interval / tick_rate)
        if int(current_day / tick_rate) % feed_interval_ticks == 0:
            # Find issues in stages["Open"] whose parent epic is in "IMPLEMENT" stage
            eligible_issues = []
            for item in stages["Open"]:
                parent_epic = next((e for e in epics if e["key"] == item.epic), None)
                if parent_epic:
                    if (
                        parent_epic["type"] == "Feature"
                        and parent_epic.get("current_stage") == "IMPLEMENTING"
                    ):
                        eligible_issues.append(item)
                    elif (
                        parent_epic["type"] == "Epic"
                        and parent_epic.get("current_stage") == "IMPLEMENT"
                    ):
                        eligible_issues.append(item)

            # Feed up to feed_count of these eligible issues
            to_move = eligible_issues[:feed_count]
            for item in to_move:
                stages["Open"].remove(item)
                item.enter_stage(1, current_day, "To Do", 0.0)
                stages["To Do"].append(item)

        # 2. Scenario 7 Upstream Starvation check:
        # If upstream can't keep up and team is starved, automatically inject techdebt or lowpriority cards directly into Ready to Implement
        if upstream_starvation:
            active_dev_wip = (
                len(stages["Implement"]) + len(stages["Code Review"]) + len(stages["test and fix"])
            )
            ready_wip = len(stages["Ready to Implement"]) + len(stages["Next"])
            # If developer pipeline is starved (less than 3 items ready/active)
            if active_dev_wip + ready_wip < 3:
                # Inject a techdebt or low priority item!
                starved_key = f"FLOW-TD-{starved_counter}"
                starved_counter += 1

                # First 40% of simulation time is techdebt, then gradually transition to low-priority features
                if current_day < (simulation_days * 0.4):
                    is_td = True
                elif current_day < (simulation_days * 0.7):
                    is_td = random.random() < 0.5
                else:
                    is_td = False

                lbls = (
                    ["filler-techdebt", "agentic-ai"]
                    if is_td
                    else ["filler-lowpriority", "agentic-ai"]
                )
                summary = (
                    "Refactor techdebt to utilize spare capacity"
                    if is_td
                    else "Low-priority feature to keep agents busy"
                )
                label_type = "agentic-ai"

                # Find an epic currently in IMPLEMENT stage, fallback to EPIC-3/EPIC-4
                active_epics = [e["key"] for e in epics if e.get("current_stage") == "IMPLEMENT"]
                epic = (
                    random.choice(active_epics)
                    if active_epics
                    else ("EPIC-4" if is_td else "EPIC-3")
                )

                new_item = SimulatedIssue(
                    starved_key,
                    summary,
                    "Story",
                    epic,
                    1,
                    label_type,
                    specific_labels=lbls,
                    work_class=WORK_CLASS_MAINTENANCE,
                )
                new_item.created_day = current_day
                new_item.enter_stage(3, current_day, "Ready to Implement", 0.0)
                stages["Ready to Implement"].append(new_item)
                backlog.append(new_item)

        # 3. Process active work in each stage
        active_stages = [
            "Specify/Plan",
            "Implement",
            "Code Review",
            "Ready for Testing",
            "test and fix",
            "Ready for release",
            "Monitor/Adapt/Learn",
        ]
        for stage in active_stages:
            stage_issues = stages[stage]
            if safe_native_ai:
                if current_day < 60.0:
                    current_capacities = {
                        "Specify/Plan": 2,
                        "Implement": 4,
                        "Code Review": 2,
                        "test and fix": 2,
                        "Monitor/Adapt/Learn": 2,
                    }
                elif current_day < 120.0:
                    current_capacities = {
                        "Specify/Plan": 2,
                        "Implement": 8,
                        "Code Review": 2,
                        "test and fix": 2,
                        "Monitor/Adapt/Learn": 2,
                    }
                else:
                    current_capacities = {
                        "Specify/Plan": 8,
                        "Implement": 12,
                        "Code Review": 12,
                        "test and fix": 12,
                        "Monitor/Adapt/Learn": 8,
                    }
                cap = current_capacities.get(stage, 999)
            else:
                cap = capacities.get(stage, 999)
            # Pull-by-priority: expedite failure demand ahead of value, value ahead
            # of filler. Stable sort keeps FIFO order within a priority tier.
            ordered = sorted(stage_issues, key=lambda it: it.priority)
            active_items = ordered[:cap]
            waiting_items = ordered[cap:]

            for item in active_items:
                if item.is_flagged:
                    item.unflag(current_day)
                item.remaining_days -= tick_rate
                if item.remaining_days < 0:
                    item.remaining_days = 0.0

            for item in waiting_items:
                if not item.is_flagged:
                    if stage == "Code Review":
                        item.flag(
                            current_day,
                            "Tech: PR / Code Review",
                            "Queue Bottleneck: Waiting for human reviewer review slot",
                        )
                    elif stage == "test and fix":
                        item.flag(
                            current_day,
                            "Tech: QA & Testing",
                            "Queue Bottleneck: Waiting for human tester capacity",
                        )
                    elif stage == "Specify/Plan":
                        item.flag(
                            current_day,
                            "Product: Missing Specs & AC",
                            "Queue Bottleneck: Product owner backlog grooming queue",
                        )

        # 4. Pull items to the next stage in reverse workflow order (Pull Kanban)
        for i in range(len(workflow_order) - 2, 0, -1):
            curr_stage = workflow_order[i]
            next_stage = workflow_order[i + 1]

            completed_in_curr = [item for item in stages[curr_stage] if item.remaining_days == 0.0]
            # Higher-priority (lower number) items claim scarce downstream slots first.
            completed_in_curr.sort(key=lambda it: it.priority)

            for item in completed_in_curr:
                # Check WIP limit
                if enable_wip_limits:
                    limit = wip_limits.get(next_stage, 999)
                    if len(stages[next_stage]) >= limit:
                        if not item.is_flagged and next_stage != "Done":
                            item.flag(
                                current_day,
                                "Other: Queue Bottleneck",
                                f"Blocked: Next stage '{next_stage}' is at its WIP limit ({limit})",
                            )
                        continue

                # Pull the item
                stages[curr_stage].remove(item)
                if item.is_flagged:
                    item.unflag(current_day)

                # Scenario 6 Regression Bug Injection check:
                # When leaving test and fix, there is a 35% chance to inject a regression Bug
                if quality_crash and curr_stage == "test and fix":
                    if random.random() < 0.35:
                        reg_key = f"FLOW-REG-{reg_bug_counter}"
                        reg_bug_counter += 1

                        # Failure demand: a production-style defect that expedites past
                        # grooming straight into the ready/dev lane, preempting stories.
                        reg_bug = SimulatedIssue(
                            reg_key,
                            f"Regression Bug introduced during hyper-speed testing of {item.key}",
                            "Bug",
                            item.epic,
                            1,
                            "agentic-ai",
                            specific_labels=["regression", "failure-demand", "agentic-ai"],
                            work_class=WORK_CLASS_FAILURE,
                        )
                        # Skip grooming: inject as expedite into Ready to Implement.
                        reg_bug.created_day = current_day
                        reg_bug.enter_stage(3, current_day, "Ready to Implement", 0.0)
                        stages["Ready to Implement"].append(reg_bug)
                        backlog.append(reg_bug)

                # Calculate duration in next stage
                base_dur = base_durations.get(next_stage, 0.0)
                if safe_native_ai:
                    if current_day < 60.0:
                        current_multipliers = {
                            "Specify/Plan": 1.0,
                            "Implement": 1.0,
                            "Code Review": 1.0,
                            "test and fix": 1.0,
                            "Ready for release": 1.0,
                            "Monitor/Adapt/Learn": 1.0,
                        }
                    elif current_day < 120.0:
                        current_multipliers = {
                            "Specify/Plan": 1.0,
                            "Implement": 0.2,
                            "Code Review": 1.0,
                            "test and fix": 0.5,
                            "Ready for release": 1.0,
                            "Monitor/Adapt/Learn": 1.0,
                        }
                    else:
                        current_multipliers = {
                            "Specify/Plan": 0.4,
                            "Implement": 0.1,
                            "Code Review": 0.2,
                            "test and fix": 0.1,
                            "Ready for release": 0.3,
                            "Monitor/Adapt/Learn": 0.2,
                        }
                    mult = current_multipliers.get(next_stage, 1.0)
                else:
                    mults = stage_multipliers.get(next_stage, {})
                    mult = mults.get(item.label_type, 1.0)
                next_duration = base_dur * mult

                item.enter_stage(i + 1, current_day, next_stage, next_duration)
                stages[next_stage].append(item)

                # Check if pulled into sprint
                current_sprint = next(
                    (s for s in sprints if s["start"] <= current_day < s["end"]), None
                )
                if current_sprint:
                    item.sprints_involved.add(current_sprint["id"])
                    if next_stage in ("Implement", "Next") and (
                        current_day - current_sprint["start"] > 2.0
                    ):
                        item.mid_sprint_sprints.add(current_sprint["id"])

        # Tick time
        current_day += tick_rate

    # Complete the unflagging for history logging but track currently flagged state
    for issue in backlog:
        if issue.is_flagged:
            issue.was_flagged_at_end = True
            issue.unflag(simulation_days)
        else:
            issue.was_flagged_at_end = False

    return backlog, epics, sprints, workflow_order


def write_simulated_csvs(out_dir, backlog, epics, sprints, workflow_order):
    os.makedirs(out_dir, exist_ok=True)

    start_date = datetime(2026, 4, 1, 9, 0)

    def day_to_date_str(day_val):
        if day_val is None:
            return ""
        dt = start_date + timedelta(days=float(day_val))
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    # 1. flow_analytics_export.csv
    # Define all possible epic and feature columns across scenarios
    export_epic_feat_cols = [
        "FUNNEL",
        "REVIEW",
        "ANALYZE",
        "READY",
        "PI PLANNING",
        "DISCOVER",
        "IMPLEMENT",
        "DELIVER",
        "DEPLOY",
        "MEASURE/LEARN",
        "DONE",
        "FEATURE FUNNEL",
        "ANALYZING",
        "PI BACKLOG",
        "IMPLEMENTING",
        "READY FOR INTEGRATION/TESTING",
        "INTEGRATING / TESTING",
        "READY FOR RELEASE",
        "RELEASE & IMPROVE",
    ]

    # 1. flow_analytics_export.csv
    flow_fields = (
        [
            "Issue Key",
            "Summary",
            "Issue Type",
            "Created Date",
            "Updated Date",
            "Current Status",
        ]
        + workflow_order
        + export_epic_feat_cols
    )
    with open(
        os.path.join(out_dir, "flow_analytics_export.csv"), "w", newline="", encoding="utf-8"
    ) as f:
        writer = csv.DictWriter(f, fieldnames=flow_fields)
        writer.writeheader()

        # Write Epics
        for epic in epics:
            created_day = epic.get("created_day", 0.0)
            transitions = epic.get("transitions", {})
            transition_days = [v for v in transitions.values() if v is not None]
            updated_day = max(transition_days) if transition_days else created_day
            status = epic.get("current_stage")

            # If the epic never entered the pipeline during the simulation, it remains in FUNNEL
            if status is None:
                if epic.get("type") == "Feature":
                    status = "FEATURE FUNNEL"
                    transitions["FEATURE FUNNEL"] = created_day
                else:
                    status = "FUNNEL"
                    transitions["FUNNEL"] = created_day
                updated_day = created_day

            row = {
                "Issue Key": epic["key"],
                "Summary": epic["summary"],
                "Issue Type": epic["type"],
                "Created Date": day_to_date_str(created_day),
                "Updated Date": day_to_date_str(updated_day),
                "Current Status": status,
            }
            for stage in export_epic_feat_cols:
                if stage in transitions:
                    row[stage] = day_to_date_str(transitions[stage])
            writer.writerow(row)

        # Write Stories & Bugs
        for issue in backlog:
            open_day = issue.transitions.get("Open", getattr(issue, "created_day", 0.0))
            last_stage = workflow_order[issue.current_stage_idx]
            updated_day = issue.transitions.get(last_stage, open_day)

            row = {
                "Issue Key": issue.key,
                "Summary": issue.summary,
                "Issue Type": issue.issue_type,
                "Created Date": day_to_date_str(open_day),
                "Updated Date": day_to_date_str(updated_day),
                "Current Status": last_stage,
            }
            for state in workflow_order:
                if state in issue.transitions:
                    row[state] = day_to_date_str(issue.transitions[state])
            writer.writerow(row)

    # 2. issue_metadata.csv
    meta_fields = [
        "Issue Key",
        "Labels",
        "Story Points",
        "Unplanned",
        "Flagged",
        "Resolution",
        "Epic Link",
        "Work Class",
        "Cost of Delay",
        "WSJF",
    ]
    with open(os.path.join(out_dir, "issue_metadata.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=meta_fields)
        writer.writeheader()

        for epic in epics:
            status = epic.get("current_stage") or "FUNNEL"
            writer.writerow(
                {
                    "Issue Key": epic["key"],
                    "Labels": epic["labels"],
                    "Story Points": "",
                    "Unplanned": "No",
                    "Flagged": "No",
                    "Resolution": status if status == "DONE" else "",
                    "Epic Link": "",
                    "Work Class": WORK_CLASS_VALUE,
                    "Cost of Delay": "",
                    "WSJF": "",
                }
            )

        for issue in backlog:
            last_stage = workflow_order[issue.current_stage_idx]
            writer.writerow(
                {
                    "Issue Key": issue.key,
                    "Labels": issue.labels,
                    "Story Points": issue.sp,
                    "Unplanned": "No",
                    "Flagged": "Yes" if getattr(issue, "was_flagged_at_end", False) else "No",
                    "Resolution": "Done" if last_stage == "Done" else "",
                    "Epic Link": issue.epic,
                    "Work Class": issue.work_class,
                    "Cost of Delay": issue.cost_of_delay,
                    "WSJF": f"{issue.wsjf:.2f}",
                }
            )

    # 3. sprint_data.csv
    sprint_fields = [
        "Issue Key",
        "Sprint ID",
        "Sprint Name",
        "Sprint State",
        "Start Date",
        "End Date",
        "Added Mid-Sprint",
    ]
    with open(os.path.join(out_dir, "sprint_data.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=sprint_fields)
        writer.writeheader()

        for issue in backlog:
            for s_id in issue.sprints_involved:
                sprint_obj = next((s for s in sprints if s["id"] == s_id), None)
                if sprint_obj:
                    mid_sprint = "Yes" if s_id in issue.mid_sprint_sprints else "No"
                    writer.writerow(
                        {
                            "Issue Key": issue.key,
                            "Sprint ID": sprint_obj["id"],
                            "Sprint Name": sprint_obj["name"],
                            "Sprint State": sprint_obj["state"],
                            "Start Date": day_to_date_str(sprint_obj["start"]),
                            "End Date": day_to_date_str(sprint_obj["end"]),
                            "Added Mid-Sprint": mid_sprint,
                        }
                    )

    # 4. issue_links.csv
    link_fields = ["Source Issue Key", "Link Type Name", "Direction", "Target Issue Key"]
    with open(os.path.join(out_dir, "issue_links.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=link_fields)
        writer.writeheader()

        for i in range(1, len(backlog) - 1, 4):
            writer.writerow(
                {
                    "Source Issue Key": backlog[i].key,
                    "Link Type Name": "Blocks",
                    "Direction": "Outward",
                    "Target Issue Key": backlog[i + 1].key,
                }
            )

    # 5. flag_history.csv
    flag_fields = ["Issue Key", "Date", "Action", "Reason", "Comment"]
    with open(os.path.join(out_dir, "flag_history.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=flag_fields)
        writer.writeheader()

        for issue in backlog:
            for flag in issue.flags:
                writer.writerow(
                    {
                        "Issue Key": issue.key,
                        "Date": day_to_date_str(flag["day"]),
                        "Action": flag["action"],
                        "Reason": flag["reason"],
                        "Comment": flag["comment"],
                    }
                )

    # 6. issue_value_analysis.csv
    val_fields = [
        "Issue Key",
        "Issue Type",
        "Summary",
        "Taxonomy Level",
        "Prescriptive Verbs",
        "Suggested Outcome Framing",
        "Rationale",
    ]
    with open(
        os.path.join(out_dir, "issue_value_analysis.csv"), "w", newline="", encoding="utf-8"
    ) as f:
        writer = csv.DictWriter(f, fieldnames=val_fields)
        writer.writeheader()

        # Add Epics
        for epic in epics:
            framing = ""
            if epic["taxonomy"] in ("Output", "Activity"):
                framing = "Coaches will be able to retrieve dashboard insights, resulting in 20% faster coaching retrospectives."
            else:
                framing = "(already outcome-oriented — no reframing needed)"

            writer.writerow(
                {
                    "Issue Key": epic["key"],
                    "Issue Type": epic["type"],
                    "Summary": epic["summary"],
                    "Taxonomy Level": epic["taxonomy"],
                    "Prescriptive Verbs": "Improve"
                    if epic["taxonomy"] == "Outcome"
                    else "Build"
                    if epic["taxonomy"] == "Output"
                    else "",
                    "Suggested Outcome Framing": framing,
                    "Rationale": f"Classified based on keywords. Level: {epic['taxonomy']}",
                }
            )

        # Add Stories — taxonomy now follows the item's Cost of Delay tier / work class,
        # so the Outcome/Activity distribution reflects real value rather than defaulting flat.
        for issue in backlog:
            if issue.work_class == WORK_CLASS_FAILURE:
                rationale = "Failure demand (rework) — does not create new value"
            elif issue.work_class == WORK_CLASS_MAINTENANCE:
                rationale = "Maintenance / filler pulled to fill spare capacity (low Cost of Delay)"
            else:
                rationale = f"Value work classified by Cost of Delay tier ({issue.cost_of_delay})"
            writer.writerow(
                {
                    "Issue Key": issue.key,
                    "Issue Type": issue.issue_type,
                    "Summary": issue.summary,
                    "Taxonomy Level": issue.taxonomy_level,
                    "Prescriptive Verbs": "",
                    "Suggested Outcome Framing": "",
                    "Rationale": rationale,
                }
            )

    # 7. issue_parents.csv
    parent_fields = [
        "Issue Key",
        "Issue Type",
        "Current Status",
        "Parent Key",
        "Parent Summary",
        "Parent Type",
    ]
    with open(os.path.join(out_dir, "issue_parents.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=parent_fields)
        writer.writeheader()

        for issue in backlog:
            parent_key = issue.epic
            parent_epic = next((e for e in epics if e["key"] == parent_key), None)
            last_stage = workflow_order[issue.current_stage_idx]

            writer.writerow(
                {
                    "Issue Key": issue.key,
                    "Issue Type": issue.issue_type,
                    "Current Status": last_stage,
                    "Parent Key": parent_key,
                    "Parent Summary": parent_epic["summary"] if parent_epic else "",
                    "Parent Type": parent_epic["type"] if parent_epic else "Epic",
                }
            )

        for epic in epics:
            if epic.get("type") == "Feature":
                parent_key = epic.get("parent_epic", "")
                parent_epic_obj = next((e for e in epics if e["key"] == parent_key), None)
                writer.writerow(
                    {
                        "Issue Key": epic["key"],
                        "Issue Type": "Feature",
                        "Current Status": epic.get("current_stage") or "FUNNEL",
                        "Parent Key": parent_key,
                        "Parent Summary": parent_epic_obj["summary"] if parent_epic_obj else "",
                        "Parent Type": "Epic" if parent_key else "",
                    }
                )


def main():
    config = load_config("simulation_config.md")

    # Try to load scenarios from config, otherwise use fallback
    scenarios = config.get("scenarios")
    if not scenarios:
        # Fallback to defaults
        scenarios = [
            {
                "folder": "1_local_optimization_trap",
                "opts": {
                    "wip_limits": False,
                    "ai_review": False,
                    "ai_test": False,
                    "quality_crash": False,
                    "upstream_starvation": False,
                },
            },
            {
                "folder": "2_balanced_flow",
                "opts": {
                    "wip_limits": True,
                    "ai_review": False,
                    "ai_test": False,
                    "quality_crash": False,
                    "upstream_starvation": False,
                },
            },
            {
                "folder": "3_traditional_baseline",
                "opts": {
                    "wip_limits": False,
                    "all_human": True,
                    "ai_review": False,
                    "ai_test": False,
                    "quality_crash": False,
                    "upstream_starvation": False,
                },
            },
            {
                "folder": "4_balanced_ai_operating_model",
                "opts": {
                    "wip_limits": False,
                    "ai_review": True,
                    "ai_test": True,
                    "quality_crash": False,
                    "upstream_starvation": False,
                },
            },
            {
                "folder": "5_hyper_velocity_disaster",
                "opts": {
                    "wip_limits": False,
                    "hyper_velocity": True,
                    "ai_review": False,
                    "ai_test": False,
                    "quality_crash": False,
                    "upstream_starvation": False,
                },
            },
            {
                "folder": "6_hyper_velocity_quality_crash",
                "opts": {
                    "wip_limits": False,
                    "hyper_velocity": True,
                    "ai_review": False,
                    "ai_test": True,
                    "quality_crash": True,
                    "upstream_starvation": False,
                },
            },
            {
                "folder": "7_techdebt_underload",
                "opts": {
                    "wip_limits": False,
                    "ai_review": True,
                    "ai_test": True,
                    "quality_crash": False,
                    "upstream_starvation": True,
                },
            },
            {
                "folder": "8_balanced_ai_with_wip_limits",
                "opts": {
                    "wip_limits": True,
                    "ai_review": True,
                    "ai_test": True,
                    "quality_crash": False,
                    "upstream_starvation": False,
                },
            },
            {
                "folder": "9_safe_native_ai_transition",
                "opts": {
                    "wip_limits": True,
                    "ai_review": True,
                    "ai_test": True,
                    "quality_crash": False,
                    "upstream_starvation": False,
                },
            },
            {
                "folder": "10_sprint_carryover_and_predictability",
                "opts": {
                    "wip_limits": False,
                    "ai_review": False,
                    "ai_test": False,
                    "quality_crash": True,
                    "upstream_starvation": False,
                },
            },
        ]

    for sc in scenarios:
        out_dir = os.path.join("sample_data", sc["folder"])
        print(f"Running simulation for scenario: {sc['folder']}...")
        backlog, epics, sprints, workflow_order = run_simulation(config, sc["opts"])
        write_simulated_csvs(out_dir, backlog, epics, sprints, workflow_order)

        # Also copy to root sample_data/ for backward compatibility (defaults to Scenario 1 trap)
        if sc["folder"] == "1_local_optimization_trap":
            write_simulated_csvs("sample_data", backlog, epics, sprints, workflow_order)


if __name__ == "__main__":
    main()
