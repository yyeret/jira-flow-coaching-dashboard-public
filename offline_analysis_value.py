#!/usr/bin/env python3
"""
Jira Value/Outcome Taxonomy Classifier
Classifies issues using the Input→Activity→Output→Outcome→Impact taxonomy.
"""

import csv
import re
import json
from pathlib import Path

import os

EXPORT_DIR = Path(os.environ.get("JIRA_DATA_DIR", "jira_flow_data"))
OUTPUT_FILE = EXPORT_DIR / "issue_value_analysis.csv"

# Quarterly bucket prefix — any epic whose summary starts with FY##Q# or Y##Q# is a
# time-box bucket, not a deliverable, regardless of what's named inside it.
# This corrects a systematic LLM (Haiku) blind spot that picks up the deliverable
# described inside the bucket and classifies it as Output instead of Activity.
QUARTERLY_BUCKET_RE = re.compile(
    r"^(FY\s*'?\d{2,4}\s*Q\d|Y\s*'?\d{2,4}\s*Q\d)",
    re.IGNORECASE,
)

# ─── Keyword signals per taxonomy level ───────────────────────────────────────
INPUT_SIGNALS = [
    r"\bhiring\b",
    r"\bheadcount\b",
    r"\bstaffing\b",
    r"\bbudget\b",
    r"\bopex\b",
    r"\bcapex\b",
    r"\bresource allocation\b",
    r"\bonboarding\b",
]
ACTIVITY_SIGNALS = [
    r"\bbug\b",
    r"\bfix\b",
    r"\bfixes\b",
    r"\bfixed\b",
    r"\bqa\b",
    r"\bqat\b",
    r"\btest\b",
    r"\btesting\b",
    r"\bregression\b",
    r"\buat\b",
    r"\bspike\b",
    r"\bdiscovery\b",
    r"\bexplore\b",
    r"\bexploring\b",
    r"\btraining\b",
    r"\blearn\b",
    r"\bonboard\b",
    r"\bmaintenance\b",
    r"\bupgrade\b",
    r"\bupgrades\b",
    r"\bmigrate\b",
    r"\brefactor\b",
    r"\bdebug\b",
    r"\binvestigate\b",
    r"\breview\b",
    r"\bauditing\b",
    r"\bsupport\b",
    r"\bmeeting\b",
    r"\bgrooming\b",
    r"\bplanning\b",
    r"\bdeploy\b",
    r"\bdeployment\b",
    r"\bconfigure\b",
    r"\bsetup\b",
    r"\bset up\b",
    r"\bmonitor\b",
    r"\bmonitoring\b",
    r"\bscan\b",
    r"\bscanning\b",
    r"\bcleanup\b",
    r"\bcleaning\b",
    r"\bpatch\b",
    r"\bhardening\b",
    r"\bdevops\b",
    r"\bci\/cd\b",
    r"\bpipeline\b",
    r"\binfrastructure\b",
    r"\bsecurity\b",
    r"\bcompliance\b",
    r"\bingest\b",
    r"\bingestion\b",
    r"\bimport\b",
    r"\bexport\b",
    r"\bextract\b",
    r"\bparsing\b",
    r"\bprocessing\b",
    r"\bsync\b",
    r"\bscrape\b",
    r"\bcrawl\b",
]
OUTPUT_SIGNALS = [
    r"\bimplement\b",
    r"\bimplementation\b",
    r"\bbuild\b",
    r"\bbuildout\b",
    r"\bcreate\b",
    r"\bdevelop\b",
    r"\badd\b",
    r"\bintegrat\b",
    r"\blaunch\b",
    r"\brelease\b",
    r"\bship\b",
    r"\bdeploy\b",
    r"\bfeature\b",
    r"\benhancement\b",
    r"\bcomponent\b",
    r"\bendpoint\b",
    r"\bapi\b",
    r"\bui\b",
    r"\bpage\b",
    r"\bdashboard\b",
    r"\bmodal\b",
    r"\bmodule\b",
    r"\bservice\b",
    r"\btool\b",
    r"\bsystem\b",
    r"\bphase\b",
    r"\brollout\b",
    r"\bupdate\b",
    r"\bupgrade\b",
    r"\bredesign\b",
    r"\brebuild\b",
    r"\bnew\b",
]
OUTCOME_SIGNALS = [
    # Clear user-capability language
    r"\busers? can\b",
    r"\bability to\b",
    r"\bempower\b",
    r"\bimprove.{0,30}experience\b",
    r"\breduce.{0,30}time\b",
    r"\bfaster.{0,20}(for users?|workflow|process)\b",
    r"\beasier.{0,20}(for users?|to use|to access)\b",
    r"\bself.?serv\b",
    r"\bself.?service\b",
    # "enable users", "allow users" — only when tied to users, not just "enable SSL"
    r"\b(enable|allow)\b.{0,30}\busers?\b",
    r"\busers?.{0,30}\b(enable|allow|can|able to)\b",
]
# Impact: ONLY when improvement/goal verb is contextually linked to a business metric.
# Bare metric words (revenue, NPS, etc.) in artifact/data context do NOT qualify.
IMPACT_SIGNALS = [
    # Improvement verb + business metric (within ~60 chars).
    # "retention" excluded here because it's also a technical term (log retention, data retention).
    r"\b(increase|improve|boost|grow|accelerate|maximise|maximize)\b.{0,60}\b(revenue|conversion|profit|nps|satisfaction|margin|ltv|roi|arr|mrr)\b",
    # Customer/user retention specifically — requires "customer" or "user" nearby
    r"\b(increase|improve|reduce|boost|grow)\b.{0,40}\b(customer|user|subscriber|reader)\b.{0,40}\bretention\b",
    r"\bretention\b.{0,40}\b(customer|user|subscriber|reader)\b",
    r"\b(reduce|minimize|minimise|decrease|lower|cut|eliminate)\b.{0,60}\b(churn|cac|friction|dropout|attrition)\b",
    r"\b(reduce|cut|lower)\b.{0,30}\bcosts?\b.{0,20}\b(by|through|via|target|goal|objective)\b",
    # Metric + explicit goal language
    r"\b(revenue|conversion|profit|nps|satisfaction|margin|ltv|roi|arr|mrr)\b.{0,60}\b(growth|increase|improvement|goal|target|objective|uplift|opportunity)\b",
    # Explicit business-goal phrases
    r"\bbusiness (result|objective|goal|kpi|impact|value proposition)\b",
    r"\b(unlock|drive|generate|capture)\b.{0,40}\b(revenue|value|growth|profit|market)\b",
    r"\breturn on investment\b",
    r"\bnet promoter\b",
    # "cost savings" / "time savings" as standalone words (not "timezone")
    r"\b(cost|time)\b.{0,20}\b(savings?|reduction goal|reduction target)\b",
]

# Negative context: metric words used as data-artifact labels rather than goals.
# If a summary matches Impact but also matches this, demote to Output/Activity.
DATA_ARTIFACT_EXCLUSION_RE = re.compile(
    r"\b(revenue|conversion|retention|churn|profit|nps|satisfaction|cost|metric|kpi)\b"
    r".{0,50}"
    r"\b(report|dashboard|csv|file|table|dataset|feed|extract|ingest|import|export|"
    r"  tableau|bi|spreadsheet|data|query|schema|field|column|view|chart|graph|summary)\b"
    r"|"
    r"\b(report|dashboard|csv|file|table|dataset|feed|extract|ingest|import|export|"
    r"tableau|bi|spreadsheet|data|query|schema|field|column|view|chart|graph|summary)\b"
    r".{0,50}"
    r"\b(revenue|conversion|retention|churn|profit|nps|satisfaction|cost|metric|kpi)\b",
    re.IGNORECASE | re.VERBOSE,
)

# Prescriptive verbs (output-framing smell)
PRESCRIPTIVE_VERBS_RE = re.compile(
    r"\b(build|create|implement|setup|set up|add|integrate|develop|launch|deploy|"
    r"configure|migrate|establish|introduce|rollout|release|redesign|rebuild|"
    r"buildout|build out)\b",
    re.IGNORECASE,
)


def compile_patterns(signals):
    return [re.compile(p, re.IGNORECASE) for p in signals]


INPUT_RE = compile_patterns(INPUT_SIGNALS)
ACTIVITY_RE = compile_patterns(ACTIVITY_SIGNALS)
OUTPUT_RE = compile_patterns(OUTPUT_SIGNALS)
OUTCOME_RE = compile_patterns(OUTCOME_SIGNALS)
IMPACT_RE = compile_patterns(IMPACT_SIGNALS)


def score(text, patterns):
    return sum(1 for p in patterns if p.search(text))


def classify(issue_key, summary, issue_type):
    """Return (taxonomy_level, prescriptive_verbs, rationale)"""
    s = summary.lower()

    # Bug type always → Activity
    if issue_type.lower() == "bug":
        verbs = ", ".join(sorted(set(PRESCRIPTIVE_VERBS_RE.findall(summary))))
        return "Activity", verbs, "Bug/defect fix — reactive work, not value creation"

    scores = {
        "Impact": score(s, IMPACT_RE),
        "Outcome": score(s, OUTCOME_RE),
        "Output": score(s, OUTPUT_RE),
        "Activity": score(s, ACTIVITY_RE),
        "Input": score(s, INPUT_RE),
    }

    # Demote Impact when metric words appear in a data-artifact context
    # (e.g. "Revenue Report", "NPS dashboard CSV") — those are Outputs, not goals
    if scores["Impact"] > 0 and DATA_ARTIFACT_EXCLUSION_RE.search(s):
        scores["Impact"] = 0

    # Impact also requires no competing strong Activity signal —
    # ingestion/processing tasks are Activities even if the subject is a metric
    if scores["Impact"] > 0 and scores["Activity"] >= 2:
        scores["Impact"] = 0

    # Priority order: Impact > Outcome > Output > Activity > Input
    for level in ["Impact", "Outcome", "Output", "Activity", "Input"]:
        if scores[level] > 0:
            verbs = ", ".join(sorted(set(PRESCRIPTIVE_VERBS_RE.findall(summary))))
            rationale = _rationale(summary, level, scores)
            return level, verbs, rationale

    # Default for epics with no strong signal
    if issue_type.lower() == "epic":
        verbs = ", ".join(sorted(set(PRESCRIPTIVE_VERBS_RE.findall(summary))))
        return (
            "Output",
            verbs,
            "Epic with no clear signal — defaulted to Output (describes a deliverable scope)",
        )

    return "Activity", "", "No strong signal — defaulted to Activity (task/work item)"


def _rationale(summary, level, scores):
    hits = [k for k, v in scores.items() if v > 0]
    signal_str = ", ".join(hits) if hits else "none"
    if level == "Activity":
        return f"Contains activity/task language (testing, QA, maintenance, discovery, bug-fix). Signal: {signal_str}"
    if level == "Output":
        return (
            f"Describes a deliverable artifact or feature to build/implement. Signal: {signal_str}"
        )
    if level == "Outcome":
        return (
            f"References user capability or measurable experience improvement. Signal: {signal_str}"
        )
    if level == "Impact":
        return f"References a business metric or bottom-line result. Signal: {signal_str}"
    if level == "Input":
        return f"References resource, budget, or staffing allocation. Signal: {signal_str}"
    return ""


# ─── Outcome framing templates ─────────────────────────────────────────────────
TEAM_CONTEXT = {
    "SPT": (
        "advertisers/media planners",
        "manage and optimize sponsored campaign budgets and placements",
    ),
    "PPD": ("advertisers/media planners", "plan and pace programmatic digital ad spend"),
    "D/GIT": ("advertisers", "activate digital and geo-targeted media buys"),
    "DevOps": ("engineering teams", "ship features reliably with automated infrastructure"),
    "QA": ("engineering teams", "release high-quality features with confidence"),
    "HEAT": (
        "all users of the HEAT platform",
        "use a secure, reliable advertising management system",
    ),
}


def extract_team(summary):
    for prefix, ctx in TEAM_CONTEXT.items():
        if re.search(rf"\b{re.escape(prefix)}\b", summary, re.IGNORECASE):
            return prefix, ctx
    return None, (None, None)


def suggest_outcome_framing(issue_key, summary, taxonomy_level):
    """Generate a suggested outcome-framing for Epics classified as Output or Activity."""
    if taxonomy_level in ("Outcome", "Impact"):
        return "(already outcome-oriented — no reframing needed)"

    team_prefix, (persona, capability_area) = extract_team(summary)

    # Strip team prefix, quarter prefix from summary
    clean = re.sub(r"^(FY\d+Q\d+\s*\|\s*)?([A-Z0-9/]+\s*\|\s*)?", "", summary).strip()
    clean = re.sub(r"\s*\|\s*.*$", "", clean).strip()  # remove trailing pipe sections

    # Remove prescriptive verbs at the start
    clean.lower()

    persona = persona or "team members"
    capability_area = capability_area or "accomplish their goals"

    # Generate framing based on taxonomy level
    if taxonomy_level == "Activity":
        # Activities are hardest to reframe — suggest the outcome they should be driving
        return (
            f"{persona.capitalize()} will be able to {capability_area} more effectively, "
            f"resulting in measurable improvement in [add KPI]. "
            f'(Note: "{clean}" describes an activity — define the user capability this work enables.)'
        )
    else:  # Output
        # Outputs → what capability does this output enable?
        return (
            f"{persona.capitalize()} will be able to {clean.lower().rstrip('.')} with confidence, "
            f"resulting in [measurable change: reduced time / increased accuracy / fewer errors]. "
            f'(Reframe from "build X" to "users can do Y because of X.")'
        )


# Keep optional classifications beside private exports, never in the source tree.
BATCH_FILES = sorted(EXPORT_DIR.glob("batch_results_*.json"))


def load_llm_epic_classifications():
    """Load LLM-classified epic results from all batch files into a dict keyed by issue key."""
    llm = {}
    for f in BATCH_FILES:
        if not f.exists():
            print(f"  WARNING: batch file not found: {f}")
            continue
        with open(f, encoding="utf-8-sig") as fh:
            for rec in json.load(fh):
                llm[rec["key"]] = rec
    print(f"  Loaded {len(llm)} LLM epic classifications from {len(BATCH_FILES)} batch files")
    return llm


def main():
    export_file = EXPORT_DIR / "flow_analytics_export.csv"

    print("Loading LLM epic classifications...")
    llm_epics = load_llm_epic_classifications()

    print(f"Reading {export_file}...")
    issues = []
    with open(export_file, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            issues.append(
                {
                    "key": row["Issue Key"],
                    "summary": row["Summary"],
                    "type": row["Issue Type"],
                    "status": row["Current Status"],
                }
            )

    print(f"Classifying {len(issues)} issues...")
    results = []
    llm_used = 0
    for i, issue in enumerate(issues):
        if i % 5000 == 0:
            print(f"  {i}/{len(issues)}...")

        is_epic = issue["type"].lower() == "epic"
        llm_rec = llm_epics.get(issue["key"]) if is_epic else None

        if llm_rec:
            # Use LLM classification for this epic
            taxonomy = llm_rec["level"]
            verbs = ""
            rationale = llm_rec.get("rationale", "")
            suggested = llm_rec.get("framing") or suggest_outcome_framing(
                issue["key"], issue["summary"], taxonomy
            )
            llm_used += 1
        else:
            # Rule-based classifier for non-Epics (and any Epics missing from LLM batches)
            taxonomy, verbs, rationale = classify(issue["key"], issue["summary"], issue["type"])
            suggested = (
                suggest_outcome_framing(issue["key"], issue["summary"], taxonomy) if is_epic else ""
            )

        # Post-processing override: quarterly bucket epics are Activity regardless of LLM/rule output.
        # Haiku systematically picks up the deliverable named inside FY##Q# buckets and says Output.
        if is_epic and taxonomy != "Activity" and QUARTERLY_BUCKET_RE.search(issue["summary"]):
            original_level = taxonomy
            taxonomy = "Activity"
            rationale = (
                f"Quarterly time-box bucket (overridden from {original_level}). " + rationale
            )
            suggested = ""

        results.append(
            {
                "Issue Key": issue["key"],
                "Issue Type": issue["type"],
                "Summary": issue["summary"],
                "Taxonomy Level": taxonomy,
                "Prescriptive Verbs": verbs,
                "Suggested Outcome Framing": suggested,
                "Rationale": rationale,
            }
        )

    print(f"  LLM classifications used for {llm_used} epics")

    print(f"Writing {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        fieldnames = [
            "Issue Key",
            "Issue Type",
            "Summary",
            "Taxonomy Level",
            "Prescriptive Verbs",
            "Suggested Outcome Framing",
            "Rationale",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    # Print summary stats
    from collections import Counter

    levels = Counter(r["Taxonomy Level"] for r in results)
    epic_levels = Counter(r["Taxonomy Level"] for r in results if r["Issue Type"].lower() == "epic")

    print("\n=== Overall Taxonomy Distribution ===")
    total = len(results)
    for level in ["Impact", "Outcome", "Output", "Activity", "Input"]:
        pct = 100 * levels[level] / total if total else 0
        print(f"  {level}: {levels[level]} ({pct:.1f}%)")

    print(f"\n=== Epic Taxonomy Distribution ({sum(epic_levels.values())} epics) ===")
    epic_total = sum(epic_levels.values())
    for level in ["Impact", "Outcome", "Output", "Activity", "Input"]:
        pct = 100 * epic_levels[level] / epic_total if epic_total else 0
        print(f"  {level}: {epic_levels[level]} ({pct:.1f}%)")

    print(f"\nDone! Output: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
