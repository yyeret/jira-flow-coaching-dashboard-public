#!/usr/bin/env python3
"""
Flow Coaching Copilot CLI & MCP Server
Provides command-line and agentic (MCP) access to flow metrics,
sprints, dependencies, blockers, and value taxonomy classifications.
"""

import os
import sys
import csv
import json
import re
import argparse
from datetime import datetime

# Scope archived projects in export JQL; public defaults exclude no projects.
DEFAULT_ARCHIVED_PROJECTS = set()

# ─── DATA LOADING & PARSING ──────────────────────────────────────────────────


def parse_date(date_str):
    if not date_str:
        return None
    try:
        clean_str = date_str.replace(" ", "T").split(".")[0]
        if "T" in clean_str:
            return datetime.strptime(clean_str, "%Y-%m-%dT%H:%M:%S")
        else:
            return datetime.strptime(clean_str, "%Y-%m-%d")
    except ValueError:
        return None


def load_csv(filepath):
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8-sig", errors="ignore") as f:
        reader = csv.DictReader(f)
        return list(reader)


class DataStore:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.issues = []
        self.sprints = []
        self.metadata = {}
        self.links = []
        self.flags = []
        self.value_analysis = {}
        self.status_columns = []
        self.load_all()

    def load_all(self):
        # 1. Load metadata
        meta_rows = load_csv(os.path.join(self.data_dir, "issue_metadata.csv"))
        for r in meta_rows:
            key = r.get("Issue Key")
            if key:
                self.metadata[key] = r

        # 2. Load value analysis (optional)
        val_rows = load_csv(os.path.join(self.data_dir, "issue_value_analysis.csv"))
        for r in val_rows:
            key = r.get("Issue Key")
            if key:
                self.value_analysis[key] = r

        # 3. Load sprint data
        self.sprints = load_csv(os.path.join(self.data_dir, "sprint_data.csv"))

        # 4. Load issue links
        self.links = load_csv(os.path.join(self.data_dir, "issue_links.csv"))

        # 5. Load flags
        self.flags = load_csv(os.path.join(self.data_dir, "flag_history.csv"))

        # 6. Load flow analytics
        flow_rows = load_csv(os.path.join(self.data_dir, "flow_analytics_export.csv"))
        if flow_rows:
            headers = flow_rows[0].keys()
            non_status = {
                "Issue Key",
                "Summary",
                "Issue Type",
                "Created Date",
                "Updated Date",
                "Current Status",
            }
            self.status_columns = [h for h in headers if h and h not in non_status]

        # Group sprint rows
        sprint_map = {}
        for s in self.sprints:
            k = s.get("Issue Key")
            if k:
                sprint_map.setdefault(k, []).append(s)

        # Build flag history map
        flag_history_map = self.build_flag_history_map()

        # Parse issues
        for row in flow_rows:
            key = row.get("Issue Key")
            if not key:
                continue
            proj = key.split("-")[0]
            if proj in DEFAULT_ARCHIVED_PROJECTS:
                continue

            meta = self.metadata.get(key, {})
            labels_str = meta.get("Labels", "")
            labels = [l.strip() for l in labels_str.split(",") if l.strip()] if labels_str else []

            # Estimate
            est = None
            for col in ["Story Points", "Story point estimate", "Estimation"]:
                val = row.get(col) or meta.get(col)
                if val:
                    try:
                        est = float(val)
                        break
                    except ValueError:
                        pass

            # Unplanned
            unplanned = "No"
            for col in ["Unplanned"]:
                val = row.get(col) or meta.get(col)
                if val and val.lower() in ("yes", "true", "1"):
                    unplanned = "Yes"
                    break

            created = parse_date(row.get("Created Date"))
            updated = parse_date(row.get("Updated Date"))

            transitions = {}
            for col in self.status_columns:
                t_date = parse_date(row.get(col))
                if t_date:
                    transitions[col] = t_date

            val_info = self.value_analysis.get(key, {})

            # Work Class / Cost of Delay: read explicit columns if present (sim ground
            # truth), otherwise infer from issue type + labels so real Jira exports work.
            work_class = (meta.get("Work Class") or "").strip()
            if not work_class:
                work_class = infer_work_class(row.get("Issue Type", ""), labels)
            cod = None
            cod_raw = meta.get("Cost of Delay")
            if cod_raw:
                try:
                    cod = float(cod_raw)
                except ValueError:
                    cod = None

            self.issues.append(
                {
                    "key": key,
                    "summary": row.get("Summary", ""),
                    "type": row.get("Issue Type", ""),
                    "created": created,
                    "updated": updated,
                    "current_status": row.get("Current Status", ""),
                    "transitions": transitions,
                    "sprints": sprint_map.get(key, []),
                    "labels": labels,
                    "estimation": est,
                    "unplanned": unplanned,
                    "work_class": work_class,
                    "cost_of_delay": cod,
                    "priority_field": (meta.get("Priority") or row.get("Priority") or "").strip(),
                    "rank": (
                        meta.get("Rank") or meta.get("Rank (LexoRank)") or row.get("Rank") or ""
                    ).strip(),
                    "resolution": meta.get("Resolution", ""),
                    "epic_link": meta.get("Epic Link", ""),
                    "flagged": meta.get("Flagged", "No"),
                    "flag_history": flag_history_map.get(
                        key,
                        {
                            "total_days": 0,
                            "reasons": [],
                            "semantic_reasons": [],
                            "reason_durations": {},
                            "semantic_durations": {},
                        },
                    ),
                    "taxonomy_level": val_info.get("Taxonomy Level", "Unclassified"),
                    "suggested_outcome_framing": val_info.get("Suggested Outcome Framing", ""),
                    "rationale": val_info.get("Rationale", ""),
                }
            )

    def build_flag_history_map(self):
        flag_history_map = {}
        grouped = {}
        max_d = datetime(2000, 1, 1)
        for f in self.flags:
            key = f.get("Issue Key")
            if key:
                grouped.setdefault(key, []).append(f)
            d = parse_date(f.get("Date") or f.get("Flag Added Date"))
            if d and d > max_d:
                max_d = d

        now = max(datetime.now(), max_d)
        for key, events in grouped.items():
            valid_events = []
            for e in events:
                d = parse_date(e.get("Date") or e.get("Flag Added Date"))
                if d:
                    valid_events.append((d, e))
            valid_events.sort(key=lambda x: x[0])

            total_ms = 0
            last_flagged_time = None
            last_event = None
            reasons = set()
            semantic_reasons = set()
            reason_durations = {}
            semantic_durations = {}

            for d, e in valid_events:
                action = e.get("Action") or ("Flagged" if e.get("Flag Added Date") else "Unflagged")
                if action == "Flagged":
                    if last_flagged_time:
                        dur = (d - last_flagged_time).total_seconds() * 1000
                        total_ms += dur
                        sem = classify_comment_semantic(
                            last_event.get("Comment", ""), last_event.get("Reason", "Impediment")
                        )
                        formal = get_formal_parent(sem)
                        reason_durations[formal] = reason_durations.get(formal, 0) + dur
                        semantic_durations[sem] = semantic_durations.get(sem, 0) + dur
                    last_flagged_time = d
                    last_event = e

                    sem = classify_comment_semantic(
                        e.get("Comment", ""), e.get("Reason", "Impediment")
                    )
                    reasons.add(get_formal_parent(sem))
                    semantic_reasons.add(sem)
                elif action == "Unflagged":
                    if last_flagged_time:
                        dur = (d - last_flagged_time).total_seconds() * 1000
                        total_ms += dur
                        sem = classify_comment_semantic(
                            last_event.get("Comment", ""), last_event.get("Reason", "Impediment")
                        )
                        formal = get_formal_parent(sem)
                        reason_durations[formal] = reason_durations.get(formal, 0) + dur
                        semantic_durations[sem] = semantic_durations.get(sem, 0) + dur
                        last_flagged_time = None
                        last_event = None

            if last_flagged_time:
                dur = (now - last_flagged_time).total_seconds() * 1000
                total_ms += dur
                sem = classify_comment_semantic(
                    last_event.get("Comment", ""), last_event.get("Reason", "Impediment")
                )
                formal = get_formal_parent(sem)
                reason_durations[formal] = reason_durations.get(formal, 0) + dur
                semantic_durations[sem] = semantic_durations.get(sem, 0) + dur

            flag_history_map[key] = {
                "total_days": total_ms / 86400000.0,
                "reasons": list(reasons),
                "semantic_reasons": list(semantic_reasons),
                "reason_durations": {k: v / 86400000.0 for k, v in reason_durations.items()},
                "semantic_durations": {k: v / 86400000.0 for k, v in semantic_durations.items()},
            }
        return flag_history_map


# ─── SEMANTIC BLOCKER CLASSIFICATION ─────────────────────────────────────────


def get_formal_parent(reason):
    if not reason:
        return "Impediment"
    if reason.startswith("Product:"):
        return "Requirements / Design"
    if reason.startswith("Tech:"):
        return "Internal Code/Issue Dependency"
    if reason.startswith("Infra:"):
        return "Environment / Infrastructure"
    if reason.startswith("External:"):
        return "External Vendor/Tool Dependency"
    if reason.startswith("Team:"):
        return "Team Dependency / Alignment"
    if reason.startswith("Other:"):
        return "Other Blocker / Uncategorized"
    return reason


def classify_comment_semantic(text, formal_reason):
    clean_reason = (formal_reason or "Impediment").strip()
    prefixes = ["Product:", "Tech:", "Infra:", "External:", "Team:", "Other:"]
    if any(clean_reason.startswith(p) for p in prefixes):
        return clean_reason
    if not text or text.strip() == "":
        if clean_reason == "Internal Code/Issue Dependency":
            return "Tech: Upstream Ticket Block"
        if clean_reason == "External Vendor/Tool Dependency":
            return "External: Third-Party API / Vendor"
        if clean_reason == "Environment / Infrastructure":
            return "Infra: Environment issue"
        if clean_reason == "Requirements / Design":
            return "Product: Missing Specs & AC"
        return clean_reason

    text_clean = text.strip().strip("\"'“”`‘")
    noise_regex = re.compile(
        r"^(?:flagged\s+as|flagged\s+because|flagged|flag\s+added|adding\s+flag|reopened\s+because|i\s+reopened\s+this\s+because|,?\s*i\s+reopened\s+this|blocker|blocked\s+because|blocked)[:,\s]*",
        re.IGNORECASE,
    )
    text_clean = noise_regex.sub("", text_clean).strip()
    text_clean = text_clean.strip("\"'“”`’ ,.-–—").strip()

    if not text_clean:
        return clean_reason

    text_lower = text_clean.lower()

    ticket_match = re.search(r"\b([a-zA-Z]+-\d+)\b", text_clean)
    if ticket_match:
        return f"Tech: Upstream Ticket Block ({ticket_match.group(1).upper()})"

    if any(k in text_lower for k in ["design", "ux", "wireframe", "mock", "ui", "prototype"]):
        return "Product: UX/Design Awaiting"
    if any(
        k in text_lower
        for k in [
            "decision",
            "prioritization",
            "priority",
            "direction",
            "product owner",
            "po",
            "pm",
            "owner",
            "on hold",
            "tbd",
            "decoupling",
            "sunset",
        ]
    ):
        return "Product: Priority Pivot / Decisions"
    if clean_reason == "Requirements / Design" or any(
        k in text_lower
        for k in [
            "details",
            "clarity",
            "ac",
            "acceptance criteria",
            "criteria",
            "edge cases",
            "spec",
            "requirement",
            "clarif",
            "question",
            "clarify",
            "confirm",
            "?",
            "ask",
            "needs definition",
            "need to groom",
            "to groom",
            "grooming",
        ]
    ):
        return "Product: Missing Specs & AC"
    if any(
        k in text_lower
        for k in [
            "vendor",
            "sailthru",
            "third-party",
            "partner",
            "external",
            "hoot",
            "comscore",
            "blueconic",
            "facebook",
            "fb",
            "alley",
        ]
    ):
        return "External: Third-Party API / Vendor"
    if any(
        k in text_lower
        for k in [
            "client",
            "customer",
            "feedback",
            "stakeholder",
            "email",
            "adrian",
            "cm ",
            "property",
        ]
    ):
        return "External: Client/Stakeholder Feed"
    if any(
        k in text_lower
        for k in [
            "environment assist",
            "vip",
            "hosting",
            "pipeline",
            "build",
            "ci/cd",
            "staging env",
            "sandbox",
            "aws",
            "cloudflare",
        ]
    ):
        return "Infra: Platform Environment Wait"
    if any(k in text_lower for k in ["down", "outage", "offline", "crash", "unreachable"]):
        return "Infra: Downtime / Outage"
    if any(
        k in text_lower
        for k in ["access", "credentials", "permission", "vpn", "password", "login", "helpdesk"]
    ):
        return "Infra: Access / Permissions"
    if any(k in text_lower for k in ["dwh", "data", "migration", "database", "db "]):
        return "Infra: DWH / Data Block"
    if any(
        k in text_lower
        for k in [
            "sick",
            "vacation",
            "holiday",
            "leave",
            "capacity",
            "out of office",
            "ooo",
            "away",
        ]
    ):
        return "Team: Resource Capacity / Out"
    if any(
        k in text_lower for k in ["discuss", "meeting", "chat", "align", "sync", "talk", "standup"]
    ):
        return "Team: Discussion / Alignment"
    if any(
        k in text_lower
        for k in [
            "released together",
            "go together",
            "co-deploy",
            "batch",
            "release window",
            "release train",
            "deploy together",
            "enotify",
        ]
    ):
        return "Tech: Co-deployment Batch Constraint"
    if any(
        k in text_lower
        for k in ["qa", "test", "verify", "validation", "bugs", "regression", "defect", "testing"]
    ):
        return "Tech: QA & Testing"
    if any(
        k in text_lower
        for k in ["pr ", "pull request", "merge", "approved", "deploy", "code review", "review"]
    ):
        return "Tech: PR / Code Review"

    if len(text_clean) <= 45:
        words = text_clean.split()
        cleaned_words = []
        for w in words:
            upper = w.upper()
            if upper in [
                "PR",
                "QA",
                "UX",
                "UI",
                "DB",
                "API",
                "SLA",
                "PROD",
                "DEV",
                "UAT",
            ] or re.match(r"^[A-Z0-9]+-\d+$", upper):
                cleaned_words.append(upper)
            else:
                cleaned_words.append(w.capitalize())
        return " ".join(cleaned_words)

    return "Other: Uncategorized Blocker"


# ─── WORK CLASS (value / failure demand / maintenance) ───────────────────────

WORK_CLASS_VALUE = "Value"
WORK_CLASS_FAILURE = "Failure Demand"
WORK_CLASS_MAINTENANCE = "Maintenance"

# Label tokens that mark non-value work when no explicit "Work Class" column exists.
FAILURE_LABEL_TOKENS = {"regression", "failure-demand", "defect", "incident", "hotfix", "prod-bug"}
MAINTENANCE_LABEL_TOKENS = {
    "filler-techdebt",
    "filler-lowpriority",
    "lowpriority",
    "keep-busy",
    "chore",
}


def infer_work_class(issue_type, labels):
    """Infer a work class from issue type + labels (for real Jira exports that lack
    an explicit Work Class column). Explicit metadata always wins over this."""
    label_set = {str(l).strip().lower() for l in (labels or [])}
    if (issue_type or "").strip().lower() == "bug" or (label_set & FAILURE_LABEL_TOKENS):
        return WORK_CLASS_FAILURE
    if label_set & MAINTENANCE_LABEL_TOKENS:
        return WORK_CLASS_MAINTENANCE
    return WORK_CLASS_VALUE


# ─── CALCULATIONS & METRICS ──────────────────────────────────────────────────


def compute_summary(store, start_state="Implement", end_state="Done"):
    wip_count = 0
    completed_cts = []

    for issue in store.issues:
        start_t = issue["transitions"].get(start_state)
        end_t = issue["transitions"].get(end_state)

        if start_t and not end_t:
            wip_count += 1
        elif start_t and end_t and end_t >= start_t:
            completed_cts.append((end_t - start_t).total_seconds() / 86400.0)

    completed_cts.sort()
    avg_ct = sum(completed_cts) / len(completed_cts) if completed_cts else 0
    p50 = completed_cts[int(len(completed_cts) * 0.5)] if completed_cts else 0
    p85 = completed_cts[int(len(completed_cts) * 0.85)] if completed_cts else 0

    return {
        "total_issues": len(store.issues),
        "active_wip": wip_count,
        "completed": len(completed_cts),
        "avg_cycle_time_days": avg_ct,
        "p50_cycle_time_days": p50,
        "p85_cycle_time_days": p85,
    }


def compute_wip_aging(store, start_state="Implement", end_state="Done"):
    wip_items = []
    # Find max date in the store issues
    max_d = datetime(2000, 1, 1)
    for issue in store.issues:
        for dt_field in ["created", "updated"]:
            dt = issue.get(dt_field)
            if dt and dt > max_d:
                max_d = dt
        for t_val in issue["transitions"].values():
            if t_val and t_val > max_d:
                max_d = t_val
    now = max(datetime.now(), max_d)
    for issue in store.issues:
        start_t = issue["transitions"].get(start_state)
        end_t = issue["transitions"].get(end_state)
        if start_t and not end_t:
            age = (now - start_t).total_seconds() / 86400.0
            wip_items.append(
                {
                    "key": issue["key"],
                    "summary": issue["summary"],
                    "type": issue["type"],
                    "status": issue["current_status"],
                    "start_date": start_t.isoformat(),
                    "age_days": age,
                    "flagged": issue["flagged"],
                    "days_blocked": issue["flag_history"]["total_days"],
                }
            )
    wip_items.sort(key=lambda x: x["age_days"], reverse=True)
    return wip_items


def compute_blockers(store):
    blockers = []
    for issue in store.issues:
        hist = issue["flag_history"]
        if hist["total_days"] > 0:
            blockers.append(
                {
                    "key": issue["key"],
                    "summary": issue["summary"],
                    "type": issue["type"],
                    "total_blocked_days": hist["total_days"],
                    "reasons": hist["reasons"],
                    "semantic_reasons": hist["semantic_reasons"],
                }
            )
    blockers.sort(key=lambda x: x["total_blocked_days"], reverse=True)
    return blockers


def compute_dependencies(store):
    blocking_map = {}
    blocked_by_map = {}
    for link in store.links:
        src = link.get("Source Issue Key")
        link_type = link.get("Link Type Name", "").lower()
        direction = link.get("Direction", "").lower()
        target = link.get("Target Issue Key")
        if not src or not target:
            continue

        if "block" in link_type:
            if direction == "inward":
                blocking_map.setdefault(target, []).append(src)
                blocked_by_map.setdefault(src, []).append(target)
            else:
                blocking_map.setdefault(src, []).append(target)
                blocked_by_map.setdefault(target, []).append(src)
        else:
            blocking_map.setdefault(src, []).append(target)
            blocked_by_map.setdefault(target, []).append(src)

    return {"blocking": blocking_map, "blocked_by": blocked_by_map}


def compute_sprints(store, end_state="Done"):
    sprints_map = {}
    for issue in store.issues:
        est = issue["estimation"] if issue["estimation"] is not None else 1
        for sp in issue["sprints"]:
            sp_id = sp.get("Sprint ID")
            if not sp_id:
                continue
            sp_start = parse_date(sp.get("Start Date"))
            sp_end = parse_date(sp.get("End Date"))
            if not sp_start or not sp_end:
                continue

            sprints_map.setdefault(
                sp_id,
                {
                    "id": sp_id,
                    "name": sp.get("Sprint Name", ""),
                    "start_date": sp.get("Start Date"),
                    "end_date": sp.get("End Date"),
                    "planned_count": 0,
                    "planned_points": 0,
                    "completed_count": 0,
                    "completed_points": 0,
                    "carryover_count": 0,
                    "carryover_points": 0,
                },
            )

            s = sprints_map[sp_id]
            s["planned_count"] += 1
            s["planned_points"] += est

            end_t = issue["transitions"].get(end_state)
            if end_t:
                grace_end = datetime.fromordinal(sp_end.toordinal() + 1)
                if end_t >= sp_start and end_t <= grace_end:
                    s["completed_count"] += 1
                    s["completed_points"] += est
                elif sp.get("Sprint State") == "active" and end_t >= sp_start:
                    s["completed_count"] += 1
                    s["completed_points"] += est
                else:
                    s["carryover_count"] += 1
                    s["carryover_points"] += est
            else:
                s["carryover_count"] += 1
                s["carryover_points"] += est

    return sorted(sprints_map.values(), key=lambda x: x["start_date"] or "")


def compute_outcomes(store):
    tax_counts = {}
    epics_framing = []

    for issue in store.issues:
        level = issue.get("taxonomy_level", "Unclassified")
        tax_counts[level] = tax_counts.get(level, 0) + 1

        if issue["type"].lower() == "epic":
            epics_framing.append(
                {
                    "key": issue["key"],
                    "summary": issue["summary"],
                    "taxonomy_level": level,
                    "suggested_outcome_framing": issue["suggested_outcome_framing"],
                    "rationale": issue["rationale"],
                }
            )

    total = sum(tax_counts.values())
    tax_percentages = {k: (v / total * 100.0) if total else 0 for k, v in tax_counts.items()}

    return {
        "distribution": tax_counts,
        "percentages": tax_percentages,
        "epics_framing": epics_framing,
    }


def _effort(issue):
    """Effort basis for value/innovation accounting: story points, falling back to 1."""
    est = issue.get("estimation")
    return est if (est is not None and est > 0) else 1


def compute_innovation_rate(store, end_state="Done"):
    """EBM-style Ability-to-Innovate metric: share of delivered effort spent on new
    value vs. failure demand (rework) vs. maintenance/filler. Story-points based."""
    buckets = {WORK_CLASS_VALUE: 0.0, WORK_CLASS_FAILURE: 0.0, WORK_CLASS_MAINTENANCE: 0.0}
    delivered = 0
    for issue in store.issues:
        if issue["type"].lower() == "epic":
            continue
        if not issue["transitions"].get(end_state):
            continue
        wc = issue.get("work_class") or WORK_CLASS_VALUE
        buckets[wc] = buckets.get(wc, 0.0) + _effort(issue)
        delivered += 1
    total = sum(buckets.values()) or 1.0
    return {
        "delivered_items": delivered,
        "innovation_rate_pct": buckets[WORK_CLASS_VALUE] / total * 100.0,
        "failure_demand_pct": buckets[WORK_CLASS_FAILURE] / total * 100.0,
        "maintenance_pct": buckets[WORK_CLASS_MAINTENANCE] / total * 100.0,
        "effort_by_class": buckets,
    }


def compute_defect_trend(store, bucket_days=7):
    """EBM Defect Trend: count of failure-demand items created per time bucket. A
    rising slope signals eroding quality (e.g., the hyper-velocity quality crash)."""
    created = []
    for issue in store.issues:
        if issue["type"].lower() == "epic":
            continue
        if (issue.get("work_class") or WORK_CLASS_VALUE) != WORK_CLASS_FAILURE:
            continue
        c = issue.get("created")
        if c:
            created.append(c)
    if not created:
        return {"buckets": [], "total_defects": 0, "trend_per_bucket": 0.0}
    created.sort()
    origin = created[0]
    counts = {}
    for c in created:
        idx = int((c - origin).total_seconds() // (bucket_days * 86400))
        counts[idx] = counts.get(idx, 0) + 1
    max_idx = max(counts.keys())
    series = [{"bucket": i, "defects": counts.get(i, 0)} for i in range(max_idx + 1)]
    # crude slope: avg of second half minus first half
    n = len(series)
    half = max(1, n // 2)
    first = sum(s["defects"] for s in series[:half]) / half
    second = sum(s["defects"] for s in series[half:]) / max(1, n - half)
    return {"buckets": series, "total_defects": len(created), "trend_per_bucket": second - first}


def compute_stage_times(store, end_state="Done"):
    """Per-stage time breakdown for completed items: median days spent in each active
    stage. Surfaces *where* time goes (e.g., Implement shrinking while Code Review
    swells) instead of only the end-to-end number."""
    cols = store.status_columns
    completed = [
        i for i in store.issues if i["type"].lower() != "epic" and i["transitions"].get(end_state)
    ]
    per_stage = {}
    for issue in completed:
        trans = sorted(
            [(s, issue["transitions"][s]) for s in cols if issue["transitions"].get(s)],
            key=lambda x: x[1],
        )
        for idx in range(len(trans) - 1):
            stage, t0 = trans[idx]
            _, t1 = trans[idx + 1]
            days = (t1 - t0).total_seconds() / 86400.0
            if days >= 0:
                per_stage.setdefault(stage, []).append(days)
    result = []
    for stage in cols:
        vals = sorted(per_stage.get(stage, []))
        if not vals:
            continue
        result.append(
            {
                "stage": stage,
                "median_days": vals[len(vals) // 2],
                "p85_days": vals[int(len(vals) * 0.85)] if vals else 0,
                "n": len(vals),
            }
        )
    return result


# Cost of Delay proxy for real Jira exports lacking a CoD column (mirrors models.js).
PRIORITY_COD_MAP = {
    "highest": 90,
    "blocker": 90,
    "critical": 90,
    "p1": 90,
    "high": 60,
    "major": 60,
    "p2": 60,
    "medium": 35,
    "normal": 35,
    "p3": 35,
    "low": 15,
    "minor": 15,
    "p4": 15,
    "lowest": 5,
    "trivial": 5,
    "p5": 5,
}


def priority_to_cod(priority_str):
    if not priority_str:
        return None
    return PRIORITY_COD_MAP.get(str(priority_str).strip().lower())


def compute_value_curve(store, end_state="Done"):
    """Cumulative value delivered over time, actual sequencing vs. the ideal. The value
    signal degrades gracefully so this works on real Jira exports, not just the sim:
      1. explicit Cost of Delay  -> WSJF-optimal ideal, true magnitudes
      2. Priority field          -> mapped to CoD magnitude, WSJF ideal
      3. backlog Rank            -> ordinal: ideal honors rank order
      4. nothing                 -> FIFO: arrival order is the implied value order
    Non-value work (failure demand / maintenance) counts as zero new value.
    NOTE: a CSV export is a point-in-time snapshot; skips are measured against current
    rank/arrival order, but mid-flight re-ranking is not visible (no rank history)."""
    items = [
        i for i in store.issues if i["type"].lower() != "epic" and i["transitions"].get(end_state)
    ]
    if not items:
        return {
            "available": False,
            "mode": None,
            "points": [],
            "cod_incurred_actual": 0,
            "cod_incurred_ideal": 0,
            "value_efficiency_pct": 0,
        }

    # Pick the best available value signal across the completed set.
    if any(i.get("cost_of_delay") is not None for i in items):
        mode = "cost_of_delay"
    elif any(priority_to_cod(i.get("priority_field")) is not None for i in items):
        mode = "priority"
    elif any(i.get("rank") for i in items):
        mode = "rank"
    else:
        mode = "fifo"

    def is_value(i):
        return (i.get("work_class") or WORK_CLASS_VALUE) == WORK_CLASS_VALUE

    value_items = [i for i in items if is_value(i)]

    if mode == "cost_of_delay":
        mag = {id(i): (i.get("cost_of_delay") or 0) for i in value_items}
    elif mode == "priority":
        mag = {id(i): (priority_to_cod(i.get("priority_field")) or 35) for i in value_items}
    elif mode == "rank":
        ranked = sorted(value_items, key=lambda i: str(i.get("rank")))
        mag = {id(i): (len(ranked) - idx) for idx, i in enumerate(ranked)}
    else:  # fifo: earliest arrival = highest implied value
        arrived = sorted(value_items, key=lambda i: i.get("created") or i["transitions"][end_state])
        mag = {id(i): (len(arrived) - idx) for idx, i in enumerate(arrived)}

    def value(i):
        return mag.get(id(i), 0) if is_value(i) else 0.0

    origin = min(i["transitions"][end_state] for i in items)

    def day(i):
        return (i["transitions"][end_state] - origin).total_seconds() / 86400.0

    actual = sorted(items, key=lambda i: i["transitions"][end_state])
    slots = [day(i) for i in actual]

    # Ideal: magnitude modes sequence by WSJF (value/size); ordinal modes by the order.
    if mode in ("cost_of_delay", "priority"):
        ideal = sorted(items, key=lambda i: value(i) / float(_effort(i)), reverse=True)
    else:
        ideal = sorted(items, key=lambda i: value(i), reverse=True)

    cum_actual = cum_ideal = 0.0
    cod_actual = cod_ideal = 0.0
    points = []
    for n in range(len(slots)):
        t = slots[n]
        va = value(actual[n])
        vi = value(ideal[n])
        cum_actual += va
        cum_ideal += vi
        cod_actual += va * t
        cod_ideal += vi * t
        points.append(
            {
                "day": round(t, 2),
                "cum_value_actual": round(cum_actual, 1),
                "cum_value_ideal": round(cum_ideal, 1),
            }
        )

    eff = (cod_ideal / cod_actual * 100.0) if cod_actual else 100.0
    return {
        "available": True,
        "mode": mode,
        "points": points,
        "total_value_delivered": round(cum_actual, 1),
        "cod_incurred_actual": round(cod_actual, 1),
        "cod_incurred_ideal": round(cod_ideal, 1),
        "value_efficiency_pct": round(eff, 1),
    }


def compute_coaching_insights(store, start_state="Implement", end_state="Done"):
    # 1. Capacity advisor (Sprint pull advisor)
    sprints = compute_sprints(store, end_state)
    recent_sprints = sprints[-5:] if len(sprints) >= 5 else sprints
    completed_counts = [s["completed_count"] for s in recent_sprints if s["completed_count"] > 0]

    recommended_pull_count = 0
    sprint_advice = "Not enough sprint data to make an recommendation."
    carryover_rate = 0.0

    if completed_counts:
        completed_counts.sort()
        idx = max(0, int(len(completed_counts) * 0.15))
        recommended_pull_count = completed_counts[idx]

        total_planned = sum(s["planned_count"] for s in recent_sprints)
        total_carryover = sum(s["carryover_count"] for s in recent_sprints)
        carryover_rate = (total_carryover / total_planned * 100.0) if total_planned else 0.0

        sprint_advice = f"Based on your last {len(completed_counts)} sprints, your 85% confidence throughput is {recommended_pull_count} items. "
        if carryover_rate > 20:
            sprint_advice += f"Currently, you carry over {carryover_rate:.1f}% of your planned sprint items, indicating chronic over-commitment. "
            sprint_advice += f"We strongly recommend capping the next sprint plan at {recommended_pull_count} items to stabilize flow."
        else:
            sprint_advice += f"You have a healthy carryover rate of {carryover_rate:.1f}%. You can confidently pull up to {recommended_pull_count} items."

    # 2. Retrospective focus advisor
    blocker_durations = {}
    for issue in store.issues:
        hist = issue["flag_history"]
        for cat, dur in hist.get("semantic_durations", {}).items():
            blocker_durations[cat] = blocker_durations.get(cat, 0) + dur

    retro_advice = "No major blockers recorded."
    sorted_blockers = []
    if blocker_durations:
        sorted_blockers = sorted(blocker_durations.items(), key=lambda x: x[1], reverse=True)
        top_cat, top_dur = sorted_blockers[0]
        total_blocker_dur = sum(blocker_durations.values())
        pct = (top_dur / total_blocker_dur * 100) if total_blocker_dur else 0
        retro_advice = (
            f"Focus your Retrospective on resolving blocks in category '{top_cat}'. "
            f"This category alone accounts for {pct:.1f}% of all blocker days ({top_dur:.1f} days). "
            f"Establishing an improvement experiment to reduce delays in '{top_cat}' is your highest leverage action."
        )

    # 3. Daily standup swarming advisor (Aging WIP)
    wip_items = compute_wip_aging(store, start_state, end_state)
    summary = compute_summary(store, start_state, end_state)
    p85_ct = summary["p85_cycle_time_days"]

    standup_alerts = []
    for item in wip_items:
        if item["age_days"] > p85_ct and p85_ct > 0:
            standup_alerts.append(
                {
                    "key": item["key"],
                    "summary": item["summary"],
                    "age_days": item["age_days"],
                    "sle_days": p85_ct,
                    "status": item["status"],
                    "days_blocked": item["days_blocked"],
                }
            )

    standup_advice = "All active WIP items are currently within typical flow limits."
    if standup_alerts:
        standup_advice = (
            f"Attention required! There are {len(standup_alerts)} items currently in progress that exceed your "
            f"85% Cycle Time SLE ({p85_ct:.1f} days). "
            f"We advise swarming immediately to finish these before starting new work."
        )

    # 4. WIP bottleneck analysis
    active_wip = summary["active_wip"]
    weekly_throughput = 0
    if len(sprints) > 0:
        recent_sprints_counts = [s["completed_count"] for s in recent_sprints]
        weekly_throughput = (
            sum(recent_sprints_counts) / (len(recent_sprints_counts) * 2)
            if recent_sprints_counts
            else 0
        )

    wip_advice = "Your WIP levels are balanced relative to throughput."
    if weekly_throughput > 0:
        wip_to_throughput_ratio = active_wip / weekly_throughput
        if wip_to_throughput_ratio > 2.5:
            wip_advice = (
                f"WIP Congestion Risk: Your current active WIP ({active_wip}) is {wip_to_throughput_ratio:.1f}x your weekly completed throughput ({weekly_throughput:.1f} items/week). "
                f"Teams are likely multitasking and context-switching. Introduce a strict WIP limit of {int(weekly_throughput * 1.5)} to speed up delivery."
            )

    # 5. Outcome Taxonomy score
    outcomes = compute_outcomes(store)
    pcts = outcomes["percentages"]
    total_taxed = sum(outcomes["distribution"].values())

    outcome_advice = "Taxonomy alignment looks balanced."
    factory_risk = False

    output_activity_pct = pcts.get("Output", 0) + pcts.get("Activity", 0)
    outcome_impact_pct = pcts.get("Outcome", 0) + pcts.get("Impact", 0)

    if output_activity_pct > 70 and total_taxed > 0:
        factory_risk = True
        epic_key = outcomes["epics_framing"][0]["key"] if outcomes["epics_framing"] else "N/A"
        outcome_advice = (
            f"Feature Factory Risk: {output_activity_pct:.1f}% of classified items are Outputs or Activities, "
            f"while only {outcome_impact_pct:.1f}% are Outcome/Impact-oriented. "
            f"We suggest auditing your Epic backlog and reframing technical outputs into behavioral outcomes. "
            f"For example, examine Epic '{epic_key}' which is currently framed as an Output."
        )

    # 6. Innovation Rate / failure-demand advisor (EBM Ability to Innovate)
    innovation = compute_innovation_rate(store, end_state)
    inv_pct = innovation["innovation_rate_pct"]
    fd_pct = innovation["failure_demand_pct"]
    mn_pct = innovation["maintenance_pct"]
    innovation_advice = f"Innovation Rate is {inv_pct:.0f}% of delivered effort going to new value."
    if fd_pct >= 15:
        innovation_advice = (
            f"Quality alarm: {fd_pct:.0f}% of delivered capacity is failure demand (rework/defects), "
            f"so only {inv_pct:.0f}% creates new value. Defects are preempting feature work — "
            f"slow down to stabilize testing before pushing more throughput."
        )
    elif mn_pct >= 30:
        innovation_advice = (
            f"Value starvation: {mn_pct:.0f}% of delivered capacity is maintenance/filler pulled to keep "
            f"people busy, with Innovation Rate at just {inv_pct:.0f}%. The downstream is starved for "
            f"high-value, well-specified work — invest upstream in refinement rather than backfilling with low-value items."
        )

    return {
        "sprint_planning": {
            "recommended_pull_count": recommended_pull_count,
            "recent_carryover_rate_pct": carryover_rate,
            "advice": sprint_advice,
        },
        "innovation_rate": {
            "innovation_rate_pct": inv_pct,
            "failure_demand_pct": fd_pct,
            "maintenance_pct": mn_pct,
            "advice": innovation_advice,
        },
        "retrospective": {
            "top_blocker_category": sorted_blockers[0][0] if sorted_blockers else None,
            "advice": retro_advice,
        },
        "daily_standup": {
            "aging_items_exceeding_sle": len(standup_alerts),
            "detailed_alerts": standup_alerts[:5],
            "advice": standup_advice,
        },
        "wip_limits": {
            "active_wip": active_wip,
            "weekly_throughput": weekly_throughput,
            "advice": wip_advice,
        },
        "outcome_alignment": {
            "feature_factory_risk": factory_risk,
            "output_activity_ratio_pct": output_activity_pct,
            "outcome_impact_ratio_pct": outcome_impact_pct,
            "advice": outcome_advice,
        },
    }


# ─── MODEL CONTEXT PROTOCOL (MCP) SERVER ─────────────────────────────────────


def handle_mcp_message(line, store):
    try:
        req = json.loads(line)
    except json.JSONDecodeError:
        return

    req_id = req.get("id")
    method = req.get("method")
    params = req.get("params", {})

    if method == "initialize":
        response = {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "jira-flow-copilot-mcp", "version": "1.0.0"},
            },
        }
    elif method == "tools/list":
        response = {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": "get_summary",
                        "description": "Retrieve flow health summary (WIP count, completed count, cycle time averages and 85th percentile).",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "start_state": {"type": "string", "default": "Implement"},
                                "end_state": {"type": "string", "default": "Done"},
                            },
                        },
                    },
                    {
                        "name": "get_wip",
                        "description": "Retrieve all currently active Work in Progress items and their ages (days elapsed since starting).",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "start_state": {"type": "string", "default": "Implement"}
                            },
                        },
                    },
                    {
                        "name": "get_blockers",
                        "description": "Retrieve historical/active blockers, classified semantically with cumulative duration blocked.",
                        "inputSchema": {"type": "object"},
                    },
                    {
                        "name": "get_dependencies",
                        "description": "Retrieve details of inward/outward blocking dependency relationships between issues.",
                        "inputSchema": {"type": "object"},
                    },
                    {
                        "name": "get_sprints",
                        "description": "Retrieve list of sprints showing planned vs. completed count/points and carryovers.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"end_state": {"type": "string", "default": "Done"}},
                        },
                    },
                    {
                        "name": "get_outcomes",
                        "description": "Retrieve value taxonomy distribution (Input/Activity/Output/Outcome/Impact) and Epic outcome framing options.",
                        "inputSchema": {"type": "object"},
                    },
                    {
                        "name": "get_innovation_rate",
                        "description": "EBM Ability-to-Innovate metric: percentage of delivered effort spent on new value vs. failure demand (rework) vs. maintenance/filler.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"end_state": {"type": "string", "default": "Done"}},
                        },
                    },
                    {
                        "name": "get_defect_trend",
                        "description": "EBM Defect Trend: count of failure-demand (defect/rework) items created per time bucket, with a rising/falling slope indicator.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"bucket_days": {"type": "number", "default": 7}},
                        },
                    },
                    {
                        "name": "get_stage_times",
                        "description": "Per-stage time breakdown (median/p85 days) for completed items, showing where cycle time accumulates across the workflow.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"end_state": {"type": "string", "default": "Done"}},
                        },
                    },
                    {
                        "name": "get_value_curve",
                        "description": "Cumulative Cost-of-Delay-weighted value delivered over time, actual vs. WSJF-optimal sequencing, plus value efficiency. Requires Cost of Delay on items.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"end_state": {"type": "string", "default": "Done"}},
                        },
                    },
                    {
                        "name": "get_coaching_insights",
                        "description": "Retrieve opinionated coaching insights and recommendations for sprint planning, standups, retrospectives, WIP limits, and taxonomy alignment.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "start_state": {"type": "string", "default": "Implement"},
                                "end_state": {"type": "string", "default": "Done"},
                            },
                        },
                    },
                ]
            },
        }
    elif method == "tools/call":
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})
        result = None

        if tool_name == "get_summary":
            result = compute_summary(
                store,
                start_state=tool_args.get("start_state", "Implement"),
                end_state=tool_args.get("end_state", "Done"),
            )
        elif tool_name == "get_wip":
            result = compute_wip_aging(store, start_state=tool_args.get("start_state", "Implement"))
        elif tool_name == "get_blockers":
            result = compute_blockers(store)
        elif tool_name == "get_dependencies":
            result = compute_dependencies(store)
        elif tool_name == "get_sprints":
            result = compute_sprints(store, end_state=tool_args.get("end_state", "Done"))
        elif tool_name == "get_outcomes":
            result = compute_outcomes(store)
        elif tool_name == "get_innovation_rate":
            result = compute_innovation_rate(store, end_state=tool_args.get("end_state", "Done"))
        elif tool_name == "get_defect_trend":
            result = compute_defect_trend(store, bucket_days=int(tool_args.get("bucket_days", 7)))
        elif tool_name == "get_stage_times":
            result = compute_stage_times(store, end_state=tool_args.get("end_state", "Done"))
        elif tool_name == "get_value_curve":
            result = compute_value_curve(store, end_state=tool_args.get("end_state", "Done"))
        elif tool_name == "get_coaching_insights":
            result = compute_coaching_insights(
                store,
                start_state=tool_args.get("start_state", "Implement"),
                end_state=tool_args.get("end_state", "Done"),
            )
        else:
            response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Tool {tool_name} not found"},
            }
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
            return

        response = {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]},
        }
    else:
        response = {"jsonrpc": "2.0", "id": req_id, "result": {}}

    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()


def run_mcp_server(store):
    sys.stderr.write("Flow Coaching Copilot MCP Server starting...\n")
    sys.stderr.flush()
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        handle_mcp_message(line, store)


# ─── MAIN CLI INTERFACE ──────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Jira Flow Coaching Copilot CLI & MCP Server")
    parser.add_argument(
        "--data-dir",
        default=".",
        help="Directory containing the Jira export CSVs (default: current directory)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available Copilot commands")

    subparsers.add_parser("summary", help="Flow metrics health summary")
    subparsers.add_parser("wip", help="Aging Work in Progress items")
    subparsers.add_parser("blockers", help="Impediment and blocker analytics")
    subparsers.add_parser("dependencies", help="Issue links and dependency tree")
    subparsers.add_parser("sprints", help="Sprint predictability & carryover metrics")
    subparsers.add_parser("outcomes", help="Value taxonomy & Epic outcome framing")
    subparsers.add_parser(
        "innovation", help="Innovation Rate: value vs. failure demand vs. maintenance (EBM)"
    )
    subparsers.add_parser(
        "defects", help="Defect trend: failure-demand items created over time (EBM)"
    )
    subparsers.add_parser("stage-times", help="Per-stage time breakdown for completed items")
    subparsers.add_parser("value-curve", help="Cumulative value delivered, actual vs. WSJF-ideal")
    subparsers.add_parser("coaching", help="Opinionated coaching insights and recommendations")
    subparsers.add_parser("mcp", help="Start stdio-based Model Context Protocol (MCP) server")

    args = parser.parse_args()

    # Load store
    store = DataStore(args.data_dir)

    if args.command == "summary":
        res = compute_summary(store)
        print(json.dumps(res, indent=2))
    elif args.command == "wip":
        res = compute_wip_aging(store)
        print(json.dumps(res, indent=2))
    elif args.command == "blockers":
        res = compute_blockers(store)
        print(json.dumps(res, indent=2))
    elif args.command == "dependencies":
        res = compute_dependencies(store)
        print(json.dumps(res, indent=2))
    elif args.command == "sprints":
        res = compute_sprints(store)
        print(json.dumps(res, indent=2))
    elif args.command == "outcomes":
        res = compute_outcomes(store)
        print(json.dumps(res, indent=2))
    elif args.command == "innovation":
        res = compute_innovation_rate(store)
        print(json.dumps(res, indent=2))
    elif args.command == "defects":
        res = compute_defect_trend(store)
        print(json.dumps(res, indent=2))
    elif args.command == "stage-times":
        res = compute_stage_times(store)
        print(json.dumps(res, indent=2))
    elif args.command == "value-curve":
        res = compute_value_curve(store)
        print(json.dumps(res, indent=2))
    elif args.command == "coaching":
        res = compute_coaching_insights(store)
        print(json.dumps(res, indent=2))
    elif args.command == "mcp":
        run_mcp_server(store)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
