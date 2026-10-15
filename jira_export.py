#!/usr/bin/env python3
import os
import requests

from jira_security import validate_jira_url
import csv
from datetime import datetime, timedelta
import argparse
import re
import time

# --- Configuration & Credentials ---
# Export these in your environment:
# export JIRA_BASE_URL="https://your-domain.atlassian.net"
# export JIRA_USER="your-email@example.com"
# export JIRA_API_TOKEN="your-api-token"

JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL", "")
JIRA_USER = os.environ.get("JIRA_USER", "")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "")


def get_auth():
    validate_jira_url(JIRA_BASE_URL)
    if not (JIRA_USER and JIRA_API_TOKEN):
        raise ValueError("Missing JIRA_USER or JIRA_API_TOKEN environment variables.")
    return (JIRA_USER, JIRA_API_TOKEN)


def parse_sprint_string(s):
    """Parse a sprint string like 'com.atlassian.greenhopper.service.sprint.Sprint@...[id=123,name=Foo,startDate=...,endDate=...]'."""

    def extract(field):
        m = re.search(rf"{field}=([^,\]]+)", s)
        return m.group(1).strip() if m else ""

    sid = extract("id")
    name = extract("name")
    state = extract("state")
    start = extract("startDate")
    end = extract("endDate")
    return sid, name, state, start, end


def extract_sprints_from_field(raw_field):
    """Extract sprint dicts from list of dicts, single dict, list of strings, or single string."""
    rows = []
    if not raw_field:
        return rows
    if not isinstance(raw_field, list):
        raw_field = [raw_field]
    for item in raw_field:
        if isinstance(item, dict):
            rows.append(
                {
                    "Sprint ID": str(item.get("id", "")),
                    "Sprint Name": item.get("name", ""),
                    "Sprint State": item.get("state", ""),
                    "Start Date": item.get("startDate", ""),
                    "End Date": item.get("endDate", ""),
                }
            )
        elif isinstance(item, str) and "name=" in item:
            sid, name, state, start, end = parse_sprint_string(item)
            rows.append(
                {
                    "Sprint ID": sid,
                    "Sprint Name": name,
                    "Sprint State": state,
                    "Start Date": start,
                    "End Date": end,
                }
            )
    return rows


def get_issue_sprints(fields):
    """Search all common sprint customfields for sprint membership."""
    sprint_field_keys = [
        "customfield_10009",
        "customfield_10020",
        "customfield_10016",
        "customfield_10004",
        "customfield_10028",
        "customfield_10010",
    ]
    for key in sprint_field_keys:
        val = fields.get(key)
        rows = extract_sprints_from_field(val)
        if rows:
            return rows
    for k, val in fields.items():
        if k.startswith("customfield_"):
            rows = extract_sprints_from_field(val)
            if rows:
                return rows
    return []


def requests_retry_get(url, max_retries=5, backoff_factor=2, **kwargs):
    if "timeout" not in kwargs:
        kwargs["timeout"] = 30

    for attempt in range(max_retries):
        try:
            response = requests.get(url, **kwargs)
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 10))
                print(f"Rate limited (429). Retrying after {retry_after} seconds...")
                time.sleep(retry_after)
                continue
            if response.status_code >= 500:
                sleep_time = backoff_factor**attempt
                print(f"Server error ({response.status_code}). Retrying in {sleep_time} seconds...")
                time.sleep(sleep_time)
                continue
            return response
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            sleep_time = backoff_factor**attempt
            print(f"Connection error/timeout: {e}. Retrying in {sleep_time} seconds...")
            time.sleep(sleep_time)

    return requests.get(url, **kwargs)


def search_jira(jql, max_results=100):
    url = f"{JIRA_BASE_URL.rstrip('/')}/rest/api/3/search/jql"
    headers = {"Accept": "application/json"}
    all_issues = []

    field_names = {}
    next_page_token = None

    while True:
        params = {
            "jql": jql,
            "maxResults": max_results,
            "expand": "names,changelog",
            "fields": "*all",
        }
        if next_page_token:
            params["nextPageToken"] = next_page_token
            print(f"Fetching issues batch with nextPageToken: {next_page_token}")
        else:
            print("Fetching issues batch (first page)...")
        response = requests_retry_get(url, headers=headers, auth=get_auth(), params=params)
        response.raise_for_status()
        data = response.json()
        if len(all_issues) == 0:
            print(f"  Jira reported total issues matching JQL: {data.get('total')}")
        if "names" in data:
            field_names.update(data["names"])

        batch = data.get("issues", [])
        all_issues.extend(batch)
        print(f"  Got {len(batch)} issues. Total so far: {len(all_issues)}")

        if data.get("isLast", True) or not data.get("nextPageToken"):
            break

        next_page_token = data.get("nextPageToken")

    return all_issues, field_names


def parse_date(date_str):
    if not date_str:
        return None
    try:
        if "-" in date_str[10:]:
            parts = date_str[10:].split("-")
            clean_str = date_str[:10] + parts[0]
        elif "+" in date_str[10:]:
            parts = date_str[10:].split("+")
            clean_str = date_str[:10] + parts[0]
        else:
            clean_str = date_str

        if "." in clean_str:
            base, ms = clean_str.split(".")
            clean_str = base + "." + ms[:3]
            return datetime.strptime(clean_str, "%Y-%m-%dT%H:%M:%S.%f")
        else:
            return datetime.strptime(clean_str, "%Y-%m-%dT%H:%M:%S")
    except Exception:
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return None


def extract_adf_text(body):
    if not body:
        return ""
    if isinstance(body, str):
        return body
    if isinstance(body, dict) and body.get("type") == "doc":
        text = ""
        for paragraph in body.get("content", []):
            if paragraph.get("type") == "paragraph":
                for text_node in paragraph.get("content", []):
                    if text_node.get("type") == "text":
                        text += text_node.get("text", "")
                text += "\n"
        return text.strip()
    return str(body)


def classify_comment(text, formal_reason=None):
    clean_reason = (formal_reason or "Impediment").strip()
    if clean_reason.startswith(("Product:", "Tech:", "Infra:", "External:", "Team:", "Other:")):
        return clean_reason

    if not text or not text.strip():
        if clean_reason == "Internal Code/Issue Dependency":
            return "Tech: Upstream Ticket Block"
        if clean_reason == "External Vendor/Tool Dependency":
            return "External: Third-Party API / Vendor"
        if clean_reason == "Environment / Infrastructure":
            return "Infra: Environment issue"
        if clean_reason == "Requirements / Design":
            return "Product: Missing Specs & AC"
        return clean_reason

    # Clean quotes and spacing first
    text_clean = text.strip().strip("\"'“”`‘’")

    # Strip noise prefixes
    noise_pattern = r"^(?:flagged\s+as|flagged\s+because|flagged|flag\s+added|adding\s+flag|reopened\s+because|i\s+reopened\s+this\s+because|,?\s*i\s+reopened\s+this|blocker|blocked\s+because|blocked)[:,\s]*"
    text_clean = re.sub(noise_pattern, "", text_clean, flags=re.IGNORECASE).strip()

    # Re-clean quotes and starting/ending punctuation (like commas, dashes)
    text_clean = re.sub(r'^[“"\'`‘,.\-–—\s]+|[”"\'`’.\-–—\s]+$', "", text_clean).strip()

    if not text_clean:
        return clean_reason

    text_lower = text_clean.lower()

    # Helper to clean and format as Title Case Category
    def clean_to_category(s):
        if not s:
            return ""
        clean = s.strip().strip("\"'.-–— ")
        words = clean.split()
        res = []
        for w in words:
            upper = w.upper()
            if upper in ["PR", "QA", "UX", "UI", "DB", "API", "SLA", "PROD", "DEV", "UAT"]:
                res.append(upper)
            elif re.match(r"^[A-Z0-9]+-\d+$", upper):
                res.append(upper)
            else:
                res.append(w.capitalize())
        return " ".join(res)

    # Check for JIRA Ticket ID first (if found anywhere, it's a tech/issue dependency)
    ticket_match = re.search(r"\b([a-zA-Z]+-\d+)\b", text_clean)
    if ticket_match:
        return f"Tech: Upstream Ticket Block ({ticket_match.group(1).upper()})"

    # 1. Specific Heuristic Classifications

    # Product: UX/Design
    if any(k in text_lower for k in ["design", "ux", "wireframe", "mock", "ui", "prototype"]):
        return "Product: UX/Design Awaiting"

    # Product: Awaiting Decision / Priority Pivot
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

    # Product: Missing Specs & AC
    if clean_reason == "Requirements / Design" or any(
        k in text_lower
        for k in [
            "details",
            "clarity",
            "ac",
            "acceptance criteria",
            "criteria",
            "spec",
            "requirement",
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

    # External: Third-Party API / Vendor
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

    # External: Client / Stakeholder Feedback
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

    # Infra: Platform Environment Wait
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

    # Infra: Downtime / Outage
    if any(k in text_lower for k in ["down", "outage", "offline", "crash", "unreachable"]):
        return "Infra: Downtime / Outage"

    # Infra: Access / Permissions
    if any(
        k in text_lower
        for k in ["access", "credentials", "permission", "vpn", "password", "login", "helpdesk"]
    ):
        return "Infra: Access / Permissions"

    # Infra: DWH / Data Block
    if any(k in text_lower for k in ["dwh", "data", "migration", "database", "db "]):
        return "Infra: DWH / Data Block"

    # Team: Resource Capacity / Out
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

    # Team: Discussion / Alignment
    if any(
        k in text_lower for k in ["discuss", "meeting", "chat", "align", "sync", "talk", "standup"]
    ):
        return "Team: Discussion / Alignment"

    # Tech: Co-deployment Batch Constraint
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

    # Tech: QA & Testing
    if any(
        k in text_lower
        for k in ["qa", "test", "verify", "validation", "bugs", "regression", "defect", "testing"]
    ):
        return "Tech: QA & Testing"

    # Tech: PR / Code Review
    if any(
        k in text_lower
        for k in ["pr ", "pull request", "merge", "approved", "deploy", "code review", "review"]
    ):
        return "Tech: PR / Code Review"

    # 2. Fallback for short comment (<= 45 chars)
    if len(text_clean) <= 45:
        return clean_to_category(text_clean)

    # 3. Fallback for other long comments
    return "Other: Uncategorized Blocker"


def parse_issues(issues, field_names):
    # Find Unplanned and Flagged field IDs
    unplanned_field_id = None
    flagged_field_id = None
    for fid, fname in field_names.items():
        if fname.lower() == "unplanned":
            unplanned_field_id = fid
        elif "flagged" in fname.lower() or "impediment" in fname.lower():
            flagged_field_id = fid

    main_rows = []
    meta_rows = []
    sprint_rows = []
    link_rows = []
    flag_rows = []
    parent_rows = []

    # Track all unique statuses to ensure our CSV has all required columns
    all_statuses = set()

    for issue in issues:
        key = issue.get("key", "")
        fields = issue.get("fields") or {}

        summary = fields.get("summary") or ""
        issuetype = (fields.get("issuetype") or {}).get("name", "")
        created = fields.get("created") or ""
        updated = fields.get("updated") or ""
        current_status = (fields.get("status") or {}).get("name", "")

        labels = fields.get("labels") or []

        # Parse Changelog to get status transition timestamps
        changelog = (issue.get("changelog") or {}).get("histories") or []
        status_transitions = {}

        # Sort changelog by created date ascending to capture earliest entry into a state
        changelog.sort(key=lambda x: x["created"])

        # Determine if we have any flagged events first to fetch comments on demand
        has_flagged_event = False
        for history in changelog:
            for item in history.get("items", []):
                if item.get("field", "").lower() in ["flagged", "impediment", "flag"]:
                    if item.get("toString"):
                        has_flagged_event = True
                        break
            if has_flagged_event:
                break

        comments = []
        if has_flagged_event:
            url = f"{JIRA_BASE_URL.rstrip('/')}/rest/api/3/issue/{key}/comment"
            try:
                res = requests_retry_get(
                    url, headers={"Accept": "application/json"}, auth=get_auth()
                )
                res.raise_for_status()
                comments_raw = res.json().get("comments") or []
                for c in comments_raw:
                    c_dt = parse_date(c.get("created"))
                    if c_dt:
                        comments.append(
                            {
                                "created_dt": c_dt,
                                "author": c.get("author", {}).get("displayName", "Unknown"),
                                "body": extract_adf_text(c.get("body")),
                                "raw_created": c.get("created"),
                            }
                        )
            except Exception as e:
                print(f"  Warning: failed to fetch comments for flagged issue {key}: {e}")

        # Collect all Link additions
        link_events = []
        for history in changelog:
            date_str = history["created"]
            history_dt = parse_date(date_str)
            for item in history.get("items", []):
                if item.get("field", "").lower() == "link":
                    to_desc = item.get("toString")
                    if to_desc:
                        link_events.append({"created_dt": history_dt, "desc": to_desc})

        for history in changelog:
            date_str = history["created"]
            for item in history.get("items", []):
                # Status transitions
                if item.get("field") == "status":
                    to_status = item.get("toString")
                    if to_status and to_status not in status_transitions:
                        status_transitions[to_status] = date_str
                        all_statuses.add(to_status)

                # Flagged/Impediment history
                if item.get("field", "").lower() in ["flagged", "impediment", "flag"]:
                    to_val = item.get("toString")
                    from_val = item.get("fromString")
                    # If to_val is empty, it was unflagged
                    if to_val:
                        flag_dt = parse_date(date_str)
                        closest_comment = None
                        closest_comment_diff = None

                        if flag_dt:
                            for c in comments:
                                diff = abs(c["created_dt"] - flag_dt)
                                if diff <= timedelta(hours=24):
                                    if closest_comment_diff is None or diff < closest_comment_diff:
                                        closest_comment_diff = diff
                                        closest_comment = c

                            closest_link = None
                            closest_link_diff = None
                            for l in link_events:
                                diff = abs(l["created_dt"] - flag_dt)
                                if diff <= timedelta(hours=24):
                                    if closest_link_diff is None or diff < closest_link_diff:
                                        closest_link_diff = diff
                                        closest_link = l

                        reason = to_val
                        comment_val = ""

                        is_blocked_link = False
                        if closest_link:
                            desc_lower = closest_link["desc"].lower()
                            if "blocked by" in desc_lower or "is blocked by" in desc_lower:
                                is_blocked_link = True

                        if is_blocked_link:
                            comment_val = closest_link["desc"]
                            if closest_comment:
                                comment_val += f" | Comment: {closest_comment['body']}"
                            reason = classify_comment(comment_val, "Internal Code/Issue Dependency")
                        elif closest_comment:
                            comment_val = closest_comment["body"]
                            reason = classify_comment(comment_val, to_val)
                        elif closest_link:
                            comment_val = closest_link["desc"]
                            reason = classify_comment(comment_val, "Other Dependency / Link")
                        else:
                            reason = classify_comment("", to_val)

                        flag_rows.append(
                            {
                                "Issue Key": key,
                                "Date": date_str,
                                "Action": "Flagged",
                                "Reason": reason,
                                "Comment": comment_val,
                            }
                        )
                    else:
                        flag_rows.append(
                            {
                                "Issue Key": key,
                                "Date": date_str,
                                "Action": "Unflagged",
                                "Reason": from_val if from_val else "Impediment",
                                "Comment": "",
                            }
                        )

        # Add the created date as the 'Open' or 'To Do' state if not in transitions
        # Adjust logic as needed per specific workflow
        if "Open" not in status_transitions:
            status_transitions["Open"] = created
            all_statuses.add("Open")

        main_row = {
            "Issue Key": key,
            "Summary": summary,
            "Issue Type": issuetype,
            "Created Date": created,
            "Updated Date": updated,
            "Current Status": current_status,
        }
        # Merge transition times
        main_row.update(status_transitions)
        main_rows.append(main_row)

        # Parse Estimation (Story Points)
        story_points = (
            fields.get("customfield_10004")
            or fields.get("customfield_10016")
            or fields.get("customfield_10026")
            or fields.get("customfield_10008")
            or ""
        )

        unplanned_val = ""
        if unplanned_field_id and unplanned_field_id in fields:
            val = fields[unplanned_field_id]
            if isinstance(val, list) and len(val) > 0:
                unplanned_val = (
                    str(val[0].get("value", val[0])) if isinstance(val[0], dict) else str(val[0])
                )
            elif isinstance(val, dict):
                unplanned_val = str(val.get("value", val))
            else:
                unplanned_val = str(val) if val is not None else ""

        flagged_val = ""
        if flagged_field_id and flagged_field_id in fields:
            val = fields[flagged_field_id]
            if isinstance(val, list) and len(val) > 0:
                flagged_val = (
                    str(val[0].get("value", val[0])) if isinstance(val[0], dict) else str(val[0])
                )
            elif isinstance(val, dict):
                flagged_val = str(val.get("value", val))
            else:
                flagged_val = str(val) if val is not None else ""

        resolution_val = ""
        resolution_field = fields.get("resolution")
        if isinstance(resolution_field, dict):
            resolution_val = resolution_field.get("name", "")

        # Collect Sprint addition events from changelog for mid-sprint scope detection
        sprint_addition_dt = {}
        for history in changelog:
            date_str = history.get("created")
            history_dt = parse_date(date_str)
            for item in history.get("items", []):
                if item.get("field", "").lower() == "sprint":
                    to_val = item.get("toString") or ""
                    if to_val and to_val not in sprint_addition_dt:
                        sprint_addition_dt[to_val] = history_dt

        # Parse Epic Link and Parent Hierarchy
        epic_link = ""
        parent_key = ""
        parent_summary = ""
        parent_type = ""

        parent = fields.get("parent")
        if parent and isinstance(parent, dict):
            epic_link = parent.get("key") or ""
            parent_key = epic_link
            parent_fields = parent.get("fields") or {}
            parent_summary = parent_fields.get("summary", "")
            parent_type = (parent_fields.get("issuetype") or {}).get("name", "")

        if not epic_link:
            epic_link = (
                fields.get("customfield_10900")
                or fields.get("customfield_10014")
                or fields.get("customfield_10005")
                or ""
            )
            if epic_link:
                parent_key = epic_link
                parent_type = "Epic"

        meta_rows.append(
            {
                "Issue Key": key,
                "Labels": ", ".join(labels),
                "Story Points": story_points,
                "Unplanned": unplanned_val,
                "Flagged": flagged_val,
                "Resolution": resolution_val,
                "Epic Link": epic_link,
            }
        )

        parent_rows.append(
            {
                "Issue Key": key,
                "Issue Type": issuetype,
                "Current Status": current_status,
                "Parent Key": parent_key,
                "Parent Summary": parent_summary,
                "Parent Type": parent_type,
            }
        )

        # Parse Issue Links
        links = fields.get("issuelinks") or []
        for link in links:
            link_type = link.get("type", {}).get("name", "")
            if "inwardIssue" in link:
                direction = link.get("type", {}).get("inward", "inward")
                target_key = link["inwardIssue"].get("key", "")
            elif "outwardIssue" in link:
                direction = link.get("type", {}).get("outward", "outward")
                target_key = link["outwardIssue"].get("key", "")
            else:
                continue

            link_rows.append(
                {
                    "Source Issue Key": key,
                    "Link Type Name": link_type,
                    "Direction": direction,
                    "Target Issue Key": target_key,
                }
            )

        # Sprint extraction with Mid-Sprint addition detection
        for sprint_info in get_issue_sprints(fields):
            s_name = sprint_info.get("Sprint Name", "")
            s_start_str = sprint_info.get("Start Date", "")
            s_start_dt = parse_date(s_start_str) if s_start_str else None

            added_mid = "No"
            add_dt = sprint_addition_dt.get(s_name)
            if add_dt and s_start_dt:
                if (add_dt - s_start_dt).total_seconds() > 86400:
                    added_mid = "Yes"

            sprint_rows.append(
                {
                    "Issue Key": key,
                    "Sprint ID": sprint_info.get("Sprint ID", ""),
                    "Sprint Name": s_name,
                    "Sprint State": sprint_info.get("Sprint State", ""),
                    "Start Date": s_start_str,
                    "End Date": sprint_info.get("End Date", ""),
                    "Added Mid-Sprint": added_mid,
                }
            )

    return (
        main_rows,
        meta_rows,
        sprint_rows,
        link_rows,
        flag_rows,
        parent_rows,
        sorted(list(all_statuses)),
    )


def fetch_board_config(board_id):
    """Fetch board configuration (column mappings & WIP limits) via Agile API."""
    url = f"{JIRA_BASE_URL.rstrip('/')}/rest/agile/1.0/board/{board_id}/configuration"
    try:
        res = requests_retry_get(url, headers={"Accept": "application/json"}, auth=get_auth())
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        print(f"  Warning: Could not fetch board config for board {board_id}: {e}")
    return None


def merge_existing_csvs(
    out_dir, main_rows, meta_rows, sprint_rows, link_rows, flag_rows, parent_rows, all_statuses
):
    """
    If existing CSVs exist in out_dir, merge/upsert the delta rows into the existing baseline dataset.
    """
    main_file = os.path.join(out_dir, "flow_analytics_export.csv")
    if not os.path.exists(main_file):
        return main_rows, meta_rows, sprint_rows, link_rows, flag_rows, parent_rows, all_statuses

    print(f"Merging delta updates into existing baseline snapshot in {out_dir}/...")
    delta_keys = {r["Issue Key"] for r in main_rows if "Issue Key" in r}

    status_set = set(all_statuses)

    # 1. Main Rows & Statuses
    existing_main = []
    with open(main_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for st in reader.fieldnames:
            if st not in [
                "Issue Key",
                "Summary",
                "Issue Type",
                "Created Date",
                "Updated Date",
                "Current Status",
            ]:
                status_set.add(st)
        for row in reader:
            if row.get("Issue Key") not in delta_keys:
                existing_main.append(row)

    merged_main = existing_main + main_rows

    # 2. Metadata Rows
    meta_file = os.path.join(out_dir, "issue_metadata.csv")
    existing_meta = []
    if os.path.exists(meta_file):
        with open(meta_file, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("Issue Key") not in delta_keys:
                    existing_meta.append(row)
    merged_meta = existing_meta + meta_rows

    # 3. Parent Rows
    parent_file = os.path.join(out_dir, "issue_parents.csv")
    existing_parents = []
    if os.path.exists(parent_file):
        with open(parent_file, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("Issue Key") not in delta_keys:
                    existing_parents.append(row)
    merged_parents = existing_parents + parent_rows

    # 4. Sprint Rows
    sprint_file = os.path.join(out_dir, "sprint_data.csv")
    existing_sprints = []
    if os.path.exists(sprint_file):
        with open(sprint_file, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("Issue Key") not in delta_keys:
                    existing_sprints.append(row)
    merged_sprints = existing_sprints + sprint_rows

    # 5. Link Rows
    link_file = os.path.join(out_dir, "issue_links.csv")
    existing_links = []
    if os.path.exists(link_file):
        with open(link_file, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("Source Issue Key") not in delta_keys:
                    existing_links.append(row)
    merged_links = existing_links + link_rows

    # 6. Flag History Rows
    flag_file = os.path.join(out_dir, "flag_history.csv")
    existing_flags = []
    if os.path.exists(flag_file):
        with open(flag_file, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("Issue Key") not in delta_keys:
                    existing_flags.append(row)
    merged_flags = existing_flags + flag_rows

    print(
        f"  Augmented: Baseline ({len(existing_main)}) + Delta ({len(main_rows)}) = Total {len(merged_main)} issues."
    )
    return (
        merged_main,
        merged_meta,
        merged_sprints,
        merged_links,
        merged_flags,
        merged_parents,
        sorted(list(status_set)),
    )


def write_csvs(
    out_dir,
    main_rows,
    meta_rows,
    sprint_rows,
    link_rows,
    flag_rows,
    parent_rows,
    all_statuses,
    board_config=None,
    is_delta=False,
):
    os.makedirs(out_dir, exist_ok=True)

    if is_delta:
        (
            main_rows,
            meta_rows,
            sprint_rows,
            link_rows,
            flag_rows,
            parent_rows,
            all_statuses,
        ) = merge_existing_csvs(
            out_dir,
            main_rows,
            meta_rows,
            sprint_rows,
            link_rows,
            flag_rows,
            parent_rows,
            all_statuses,
        )

    # 1. Main Export
    main_fields = [
        "Issue Key",
        "Summary",
        "Issue Type",
        "Created Date",
        "Updated Date",
        "Current Status",
    ] + all_statuses
    with open(
        os.path.join(out_dir, "flow_analytics_export.csv"), "w", newline="", encoding="utf-8"
    ) as f:
        writer = csv.DictWriter(f, fieldnames=main_fields)
        writer.writeheader()
        for row in main_rows:
            writer.writerow(row)

    # 2. Metadata Export
    meta_fields = [
        "Issue Key",
        "Labels",
        "Story Points",
        "Unplanned",
        "Flagged",
        "Resolution",
        "Epic Link",
    ]
    with open(os.path.join(out_dir, "issue_metadata.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=meta_fields)
        writer.writeheader()
        writer.writerows(meta_rows)

    # 3. Sprint Export
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
        writer.writerows(sprint_rows)

    # 4. Links Export
    link_fields = ["Source Issue Key", "Link Type Name", "Direction", "Target Issue Key"]
    with open(os.path.join(out_dir, "issue_links.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=link_fields)
        writer.writeheader()
        writer.writerows(link_rows)

    # 5. Flag History Export
    flag_fields = ["Issue Key", "Date", "Action", "Reason", "Comment"]
    with open(os.path.join(out_dir, "flag_history.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=flag_fields)
        writer.writeheader()
        writer.writerows(flag_rows)

    # 6. Parent Hierarchy Export
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
        writer.writerows(parent_rows)

    # 7. Board Config Export (if board_config provided)
    if board_config:
        import json

        with open(os.path.join(out_dir, "board_config.json"), "w", encoding="utf-8") as f:
            json.dump(board_config, f, indent=2)

    print(f"Successfully wrote exports to {out_dir}/")


def modify_jql_defaults(jql, auth, since_days=None):
    # 1. Archive filter logic
    try:
        url = f"{JIRA_BASE_URL.rstrip('/')}/rest/api/3/project"
        res = requests.get(url, auth=auth, headers={"Accept": "application/json"}, timeout=30)
        if res.status_code == 200:
            projects = res.json()
            archive_keys = []
            for p in projects:
                name = p.get("name", "").lower()
                key = p.get("key", "").lower()
                if "archive" in name or "archive" in key:
                    archive_keys.append(p.get("key"))
            if archive_keys:
                keys_str = ", ".join(f"'{k}'" for k in archive_keys)
                jql = f"({jql}) AND project NOT IN ({keys_str})"
                print(f"  Omitted archive projects: {', '.join(archive_keys)}")
    except Exception as e:
        print(f"  Warning: Could not fetch project list for archive filtering: {e}")

    # 2. Delta date range filter logic
    if since_days:
        jql = f"({jql}) AND updated >= -{since_days}d"
        print(f"  Applied incremental delta constraint: updated >= -{since_days}d")
    elif "created" not in jql.lower() and "updated" not in jql.lower():
        jql = f"({jql}) AND (created >= -365d OR updated >= -365d)"
        print("  Applied default last-year constraint.")

    print(f"  Final JQL: {jql}")
    return jql


def main():
    parser = argparse.ArgumentParser(description="Export Jira data for Flow Analytics Dashboard")
    parser.add_argument(
        "--jql",
        required=True,
        help="JQL query to fetch issues (e.g., 'project=ABC AND issuetype in (Story,Bug)')",
    )
    parser.add_argument("--out-dir", default="data_export", help="Output directory for the CSVs")
    parser.add_argument(
        "--batch-size", type=int, default=50, help="Batch size for fetching issues (default: 50)"
    )
    parser.add_argument(
        "--board-id",
        type=int,
        default=None,
        help="Optional Agile Board ID to export board_config.json",
    )
    parser.add_argument(
        "--since-days",
        type=int,
        default=None,
        help="Optional incremental delta export (e.g. --since-days 7)",
    )
    args = parser.parse_args()

    auth = get_auth()
    jql = modify_jql_defaults(args.jql, auth, since_days=args.since_days)
    issues, field_names = search_jira(jql, max_results=args.batch_size)
    print(f"Fetched {len(issues)} issues.")

    main_rows, meta_rows, sprint_rows, link_rows, flag_rows, parent_rows, all_statuses = (
        parse_issues(issues, field_names)
    )

    board_config = fetch_board_config(args.board_id) if args.board_id else None

    write_csvs(
        args.out_dir,
        main_rows,
        meta_rows,
        sprint_rows,
        link_rows,
        flag_rows,
        parent_rows,
        all_statuses,
        board_config=board_config,
        is_delta=bool(args.since_days),
    )


if __name__ == "__main__":
    main()
