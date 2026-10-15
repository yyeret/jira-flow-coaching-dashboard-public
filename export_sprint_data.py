#!/usr/bin/env python3
"""
Standalone sprint membership exporter for the Flow Dashboard.

Tries three strategies in order:
  1. customfield_10020 as list-of-dicts (Jira Cloud default)
  2. customfield_10020 as list-of-strings (some Jira configs serialize it this way)
  3. Agile board API  (/rest/agile/1.0/board/{boardId}/sprint + issue membership)

Usage:
  export JIRA_BASE_URL=https://your-domain.atlassian.net
  export JIRA_USER=you@example.com
  export JIRA_API_TOKEN=yourtoken

  # Diagnose what the field looks like (sample 5 issues):
  python export_sprint_data.py --jql "project=PROJ" --diagnose

  # Full export:
  python export_sprint_data.py --jql "project=PROJ" \
      --out "path/to/sprint_data.csv"

  # If strategies 1+2 return nothing, supply a board ID from your Jira URL:
  python export_sprint_data.py --jql "project=PROJ" \
      --board-id 123 --out "path/to/sprint_data.csv"
"""

import os
import re
import csv
import sys
import json
import time
import argparse
import requests

from jira_security import validate_jira_url

JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL", "").rstrip("/")
JIRA_USER = os.environ.get("JIRA_USER", "")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "")


def auth():
    validate_jira_url(JIRA_BASE_URL)
    if not (JIRA_USER and JIRA_API_TOKEN):
        sys.exit("ERROR: set JIRA_USER and JIRA_API_TOKEN environment variables.")
    return (JIRA_USER, JIRA_API_TOKEN)


def get(url, params=None):
    """GET with simple retry on 429/5xx."""
    for attempt in range(5):
        r = requests.get(
            url, auth=auth(), headers={"Accept": "application/json"}, params=params, timeout=30
        )
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", 10))
            print(f"  Rate-limited, waiting {wait}s…")
            time.sleep(wait)
            continue
        if r.status_code >= 500:
            time.sleep(2**attempt)
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()


# ---------------------------------------------------------------------------
# Strategy 1 + 2: pull sprint info from customfield_10020 on each issue
# ---------------------------------------------------------------------------


def fetch_issues_with_sprints(jql, batch_size=50):
    """Return list of raw Jira issues fetched with fields=*all."""
    url = f"{JIRA_BASE_URL}/rest/api/3/search/jql"
    all_issues = []
    next_token = None
    while True:
        params = {"jql": jql, "maxResults": batch_size, "fields": "*all", "expand": "names"}
        if next_token:
            params["nextPageToken"] = next_token
        print(f"  Fetching issues batch… (so far: {len(all_issues)})")
        data = get(url, params)
        batch = data.get("issues", [])
        all_issues.extend(batch)
        if data.get("isLast", True) or not data.get("nextPageToken"):
            break
        next_token = data["nextPageToken"]
    return all_issues


def parse_sprint_string(s):
    """Parse a sprint string like 'com.atlassian.greenhopper.service.sprint.Sprint@...[...,name=Foo,startDate=...,endDate=...,...]'."""

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
    """Handle both dict-list and string-list variants of customfield_10020."""
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


def build_rows_from_issues(issues):
    rows = []
    for issue in issues:
        key = issue["key"]
        fields = issue.get("fields", {})
        for s in get_issue_sprints(fields):
            rows.append({"Issue Key": key, "Added Mid-Sprint": "No", **s})
    return rows


# ---------------------------------------------------------------------------
# Strategy 3: Agile board API
# ---------------------------------------------------------------------------


def fetch_board_sprints(board_id):
    """Return list of sprint dicts from the Agile board API."""
    url = f"{JIRA_BASE_URL}/rest/agile/1.0/board/{board_id}/sprint"
    sprints = []
    start = 0
    while True:
        data = get(url, params={"startAt": start, "maxResults": 50})
        sprints.extend(data.get("values", []))
        if data.get("isLast", True):
            break
        start += 50
    return sprints


def fetch_sprint_issues(sprint_id):
    """Return list of issue keys in a given sprint."""
    url = f"{JIRA_BASE_URL}/rest/agile/1.0/sprint/{sprint_id}/issue"
    keys = []
    start = 0
    while True:
        data = get(url, params={"startAt": start, "maxResults": 100, "fields": "summary"})
        keys.extend(i["key"] for i in data.get("issues", []))
        total = data.get("total", 0)
        start += 100
        if start >= total:
            break
    return keys


def build_rows_from_board(board_id):
    print(f"  Fetching sprints from board {board_id} via Agile API…")
    sprints = fetch_board_sprints(board_id)
    print(f"  Found {len(sprints)} sprints.")
    rows = []
    for sp in sprints:
        sid = str(sp.get("id", ""))
        name = sp.get("name", "")
        state = sp.get("state", "")
        start = sp.get("startDate", "")
        end = sp.get("endDate", "")
        print(f"    Sprint: {name} ({state}) — fetching members…")
        keys = fetch_sprint_issues(sid)
        print(f"      {len(keys)} issues")
        for key in keys:
            rows.append(
                {
                    "Issue Key": key,
                    "Sprint ID": sid,
                    "Sprint Name": name,
                    "Sprint State": state,
                    "Start Date": start,
                    "End Date": end,
                    "Added Mid-Sprint": "No",
                }
            )
    return rows


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def diagnose(jql):
    print("\n=== DIAGNOSE: sampling 5 issues to inspect customfield_10009 & customfield_10020 ===")
    url = f"{JIRA_BASE_URL}/rest/api/3/search/jql"
    data = get(
        url, {"jql": jql, "maxResults": 5, "fields": "customfield_10009,customfield_10020,summary"}
    )
    for issue in data.get("issues", []):
        key = issue["key"]
        cf9 = issue.get("fields", {}).get("customfield_10009")
        cf20 = issue.get("fields", {}).get("customfield_10020")
        print(f"\n  {key}:")
        print(f"    customfield_10009: {json.dumps(cf9, indent=6)[:300]}")
        print(f"    customfield_10020: {json.dumps(cf20, indent=6)[:300]}")
    print("\n  If all values are null → the sprint field is not populated for this JQL.")
    print("  If values are strings → use this script as-is (strategy 2 handles strings).")
    print("  If values are dicts   → strategy 1 will work; re-run without --diagnose.\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def write_csv(rows, out_path):
    fields = [
        "Issue Key",
        "Sprint ID",
        "Sprint Name",
        "Sprint State",
        "Start Date",
        "End Date",
        "Added Mid-Sprint",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {len(rows)} sprint membership rows to: {out_path}")


def modify_jql_defaults(jql, user_auth):
    # 1. Archive filter logic
    try:
        url = f"{JIRA_BASE_URL.rstrip('/')}/rest/api/3/project"
        res = requests.get(url, auth=user_auth, headers={"Accept": "application/json"}, timeout=30)
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

    # 2. Date range filter logic (last year of data)
    if "created" not in jql.lower() and "updated" not in jql.lower():
        jql = f"({jql}) AND (created >= -365d OR updated >= -365d)"
        print("  Applied default last-year constraint.")

    print(f"  Final JQL: {jql}")
    return jql


def main():
    parser = argparse.ArgumentParser(description="Export sprint membership for Flow Dashboard")
    parser.add_argument("--jql", required=True, help="JQL to select issues")
    parser.add_argument("--out", default="sprint_data.csv", help="Output CSV path")
    parser.add_argument(
        "--board-id",
        type=int,
        default=None,
        help="Jira Agile board ID (fallback if customfield_10020 is empty)",
    )
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Sample 5 issues and print what customfield_10020 looks like, then exit",
    )
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()

    if not JIRA_BASE_URL:
        sys.exit("ERROR: set JIRA_BASE_URL environment variable.")

    user_auth = auth()
    jql = modify_jql_defaults(args.jql, user_auth)

    if args.diagnose:
        diagnose(jql)
        return

    # Try strategy 1 + 2 first
    print("Strategy 1/2: fetching issues and reading customfield_10020…")
    issues = fetch_issues_with_sprints(jql, args.batch_size)
    print(f"  Fetched {len(issues)} issues.")
    rows = build_rows_from_issues(issues)

    if rows:
        print(f"  Got {len(rows)} sprint membership rows from field data.")
        write_csv(rows, args.out)
        return

    print("  customfield_10020 returned no data for any issue.")

    # Fallback: strategy 3
    if args.board_id:
        print(f"\nStrategy 3: using Agile board API (board {args.board_id})…")
        rows = build_rows_from_board(args.board_id)
        if rows:
            write_csv(rows, args.out)
        else:
            print("Board API also returned no sprint data. Check the board ID.")
    else:
        print("\nNext step: find your board ID in the Jira URL (?rapidView=NNN or /boards/NNN)")
        print("Then re-run with:  --board-id NNN")
        print("Or run with --diagnose to inspect what the sprint field actually contains.")


if __name__ == "__main__":
    main()
