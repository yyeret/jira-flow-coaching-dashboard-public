#!/usr/bin/env python3
"""Lightweight export of the story->epic (parent) relationship only.

The main jira_export.py fetches *all fields but never writes the Jira `parent`
(Epic Link) field, so the existing CSVs can't map a story to its epic. Rather
than re-running the full ~50k-issue export, this script fetches ONLY the
`parent` field for every issue matching the JQL and writes a small
`issue_parents.csv` that the epic dashboard joins against the existing
flow_analytics_export.csv. The big exports are left untouched.

Usage (same env vars as jira_export.py):
  export JIRA_BASE_URL="https://your-domain.atlassian.net"
  export JIRA_USER="you@example.com"
  export JIRA_API_TOKEN="..."

  python export_epic_parents.py --jql "project=VO" \
      --out-dir "H:/My Drive/.../jira-flow-coaching"
"""

import os
import csv
import time
import argparse
import requests

from jira_security import validate_jira_url

JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL", "")
JIRA_USER = os.environ.get("JIRA_USER", "")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "")


def get_auth():
    validate_jira_url(JIRA_BASE_URL)
    if not (JIRA_USER and JIRA_API_TOKEN):
        raise ValueError("Missing JIRA_USER or JIRA_API_TOKEN environment variables.")
    return (JIRA_USER, JIRA_API_TOKEN)


def requests_retry_get(url, max_retries=5, backoff_factor=2, **kwargs):
    kwargs.setdefault("timeout", 30)
    for attempt in range(max_retries):
        try:
            response = requests.get(url, **kwargs)
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 10))
                print(f"Rate limited (429). Retrying after {retry_after}s...")
                time.sleep(retry_after)
                continue
            if response.status_code >= 500:
                sleep_time = backoff_factor**attempt
                print(f"Server error ({response.status_code}). Retrying in {sleep_time}s...")
                time.sleep(sleep_time)
                continue
            return response
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            sleep_time = backoff_factor**attempt
            print(f"Connection error/timeout: {e}. Retrying in {sleep_time}s...")
            time.sleep(sleep_time)
    return requests.get(url, **kwargs)


def fetch_parents(jql, max_results=100):
    """Page through all issues requesting only the parent field (and a few
    cheap context fields) and yield flattened parent rows."""
    url = f"{JIRA_BASE_URL.rstrip('/')}/rest/api/3/search/jql"
    headers = {"Accept": "application/json"}
    next_page_token = None
    rows = []

    while True:
        params = {
            "jql": jql,
            "maxResults": max_results,
            # parent covers both team-managed and company-managed epic links in
            # the modern API. issuetype/status/summary are cheap context.
            "fields": "parent,issuetype,status,summary",
        }
        if next_page_token:
            params["nextPageToken"] = next_page_token
            print(f"Fetching batch (token {next_page_token[:12]}...)")
        else:
            print("Fetching first batch...")

        response = requests_retry_get(url, headers=headers, auth=get_auth(), params=params)
        response.raise_for_status()
        data = response.json()

        if not rows:
            print(f"  Jira reports total matching JQL: {data.get('total', 'unknown')}")

        for issue in data.get("issues", []):
            fields = issue.get("fields") or {}
            parent = fields.get("parent") or {}
            parent_fields = parent.get("fields") or {}
            rows.append(
                {
                    "Issue Key": issue.get("key", ""),
                    "Issue Type": (fields.get("issuetype") or {}).get("name", ""),
                    "Current Status": (fields.get("status") or {}).get("name", ""),
                    "Parent Key": parent.get("key", ""),
                    "Parent Summary": parent_fields.get("summary", ""),
                    "Parent Type": (parent_fields.get("issuetype") or {}).get("name", ""),
                }
            )

        print(f"  Got {len(data.get('issues', []))} issues. Total so far: {len(rows)}")

        if data.get("isLast", True) or not data.get("nextPageToken"):
            break
        next_page_token = data.get("nextPageToken")

    return rows


def modify_jql_defaults(jql, auth):
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

    # 2. Date range filter logic (last year of data)
    if "created" not in jql.lower() and "updated" not in jql.lower():
        jql = f"({jql}) AND (created >= -365d OR updated >= -365d)"
        print("  Applied default last-year constraint.")

    print(f"  Final JQL: {jql}")
    return jql


def main():
    parser = argparse.ArgumentParser(
        description="Export only the story->epic parent relationship only."
    )
    parser.add_argument("--jql", required=True, help="JQL (e.g. 'project=VO')")
    parser.add_argument("--out-dir", default=".", help="Output directory for issue_parents.csv")
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()

    auth = get_auth()
    jql = modify_jql_defaults(args.jql, auth)

    rows = fetch_parents(jql, max_results=args.batch_size)

    os.makedirs(args.out_dir, exist_ok=True)
    out_path = os.path.join(args.out_dir, "issue_parents.csv")
    fieldnames = [
        "Issue Key",
        "Issue Type",
        "Current Status",
        "Parent Key",
        "Parent Summary",
        "Parent Type",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    with_parent = sum(1 for r in rows if r["Parent Key"])
    print(f"\nWrote {len(rows)} rows to {out_path}")
    print(
        f"  {with_parent} have a parent; {len(rows) - with_parent} are top-level (epics/orphans)."
    )


if __name__ == "__main__":
    main()
