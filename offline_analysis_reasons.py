import csv
import argparse
from collections import defaultdict
import os
from datetime import datetime


def parse_date(date_str):
    if not date_str:
        return None
    try:
        # Strip trailing timezone info if it has -XXXX or +XXXX
        clean_str = date_str
        offset_mins = 0
        if "-" in date_str[10:]:
            parts = date_str[10:].split("-")
            clean_str = date_str[:10] + parts[0]
            tz = parts[1]
            if ":" in tz:
                h, m = tz.split(":")
                offset_mins = int(h) * 60 + int(m)
            else:
                offset_mins = int(tz[:2]) * 60 + int(tz[2:])
            offset_mins = -offset_mins
        elif "+" in date_str[10:]:
            parts = date_str[10:].split("+")
            clean_str = date_str[:10] + parts[0]
            tz = parts[1]
            if ":" in tz:
                h, m = tz.split(":")
                offset_mins = int(h) * 60 + int(m)
            else:
                offset_mins = int(tz[:2]) * 60 + int(tz[2:])

        # Strip millisecond parts if they are too long or vary
        if "." in clean_str:
            base, ms = clean_str.split(".")
            clean_str = base + "." + ms[:3]  # keep up to 3 digits
            dt = datetime.strptime(clean_str, "%Y-%m-%dT%H:%M:%S.%f")
        else:
            dt = datetime.strptime(clean_str, "%Y-%m-%dT%H:%M:%S")

        return dt
    except Exception:
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except:
            return None


def main():
    parser = argparse.ArgumentParser(
        description="Analyze reasons when issues are marked as flagged"
    )
    parser.add_argument(
        "--data-dir", required=True, help="Path to the directory containing the CSV exports"
    )
    args = parser.parse_args()

    flag_path = os.path.join(args.data_dir, "flag_history.csv")
    flow_path = os.path.join(args.data_dir, "flow_analytics_export.csv")

    if not os.path.exists(flag_path):
        print(f"Could not find flag_history.csv in directory: {args.data_dir}")
        return

    # 1. Load issue lifecycle details from flow_analytics_export.csv
    issue_lifecycle = {}
    done_statuses = ["Done", "Closed", "Complete", "Resolved", "Released"]

    if os.path.exists(flow_path):
        print("Reading flow_analytics_export.csv to get issue lifecycles...")
        with open(flow_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = row.get("Issue Key")
                if not key:
                    continue
                created_dt = parse_date(row.get("Created Date"))

                # Find resolution/completion date
                resolved_dt = None
                for col in done_statuses:
                    val = row.get(col)
                    if val:
                        dt = parse_date(val)
                        if dt:
                            if resolved_dt is None or dt < resolved_dt:
                                resolved_dt = dt

                issue_lifecycle[key] = {
                    "created": created_dt,
                    "resolved": resolved_dt,
                    "status": row.get("Current Status", ""),
                }
    else:
        print(
            "Warning: flow_analytics_export.csv not found. Flagged duration capping won't be applied."
        )

    # 2. Group flag history events by issue key
    grouped_flags = defaultdict(list)
    with open(flag_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = row.get("Issue Key")
            if key:
                grouped_flags[key].append(row)

    # 3. Find max date in flag history to bound active flags
    all_dates = []
    for key, events in grouped_flags.items():
        for e in events:
            dt = parse_date(e.get("Date"))
            if dt:
                all_dates.append(dt)
    max_date = max(all_dates) if all_dates else datetime.now()

    # 4. Analyze reasons and durations
    reason_flag_count = defaultdict(int)
    reason_total_days = defaultdict(float)
    reason_issues = defaultdict(set)
    total_flagged_segments = 0

    for key, events in grouped_flags.items():
        # Sort events by date
        sorted_events = []
        for e in events:
            dt = parse_date(e.get("Date"))
            if dt:
                sorted_events.append((dt, e))
        sorted_events.sort(key=lambda x: x[0])

        # Lifecycle fallback
        lifecycle = issue_lifecycle.get(key, {})
        created_date = lifecycle.get("created")
        resolved_date = lifecycle.get("resolved")

        # If the first event is an Unflagged action, reconstruct the Flagged action
        if sorted_events and sorted_events[0][1].get("Action") == "Unflagged":
            # Reconstruct Flagged event at issue created date (or 1 second before the unflagged date if created date is missing/after)
            unflag_dt = sorted_events[0][0]
            flag_dt = created_date if created_date and created_date < unflag_dt else unflag_dt
            reason = sorted_events[0][1].get("Reason", "Impediment").strip() or "Impediment"
            # Insert virtual Flagged event
            sorted_events.insert(
                0,
                (
                    flag_dt,
                    {
                        "Issue Key": key,
                        "Date": flag_dt.isoformat(),
                        "Action": "Flagged",
                        "Reason": reason,
                        "is_virtual": True,
                    },
                ),
            )

        last_flagged_time = None
        last_reason = None

        for dt, e in sorted_events:
            action = e.get("Action")
            reason = e.get("Reason", "").strip()
            if not reason:
                reason = "Unknown / No Reason"

            if action == "Flagged":
                # Close previous segment if it exists
                if last_flagged_time:
                    days = (dt - last_flagged_time).total_seconds() / 86400.0
                    reason_total_days[last_reason] += max(0.0, days)

                last_flagged_time = dt
                last_reason = reason
                reason_flag_count[reason] += 1
                reason_issues[reason].add(key)
                total_flagged_segments += 1

            elif action == "Unflagged" or not action:
                if last_flagged_time:
                    days = (dt - last_flagged_time).total_seconds() / 86400.0
                    reason_total_days[last_reason] += max(0.0, days)
                    last_flagged_time = None
                    last_reason = None

        # If still flagged at the end of history
        if last_flagged_time:
            # End boundary: if the issue is resolved/done, cap at resolution date. Otherwise use max date in dataset.
            end_boundary = (
                resolved_date if resolved_date and resolved_date > last_flagged_time else max_date
            )
            days = (end_boundary - last_flagged_time).total_seconds() / 86400.0
            reason_total_days[last_reason] += max(0.0, days)

    print(
        "\n========================================================================================================="
    )
    print(f"Total Unique Flagged Issues: {len(grouped_flags)}")
    print(f"Total Flagged Segments (Events): {total_flagged_segments}")
    print(
        "========================================================================================================="
    )
    print("\n--- Refined Flagged Reason Analysis ---")
    print(
        f"{'Flagged Reason':<55} | {'Flag Events':<12} | {'Unique Issues':<15} | {'Total Days':<12} | {'Avg Days/Flag':<15}"
    )
    print("-" * 120)

    # Sort reasons by total days descending
    sorted_reasons = sorted(
        reason_flag_count.keys(), key=lambda r: reason_total_days[r], reverse=True
    )

    for reason in sorted_reasons:
        events_cnt = reason_flag_count[reason]
        issues_cnt = len(reason_issues[reason])
        tot_days = reason_total_days[reason]
        avg_days = tot_days / events_cnt if events_cnt > 0 else 0

        print(
            f"{reason:<55} | {events_cnt:<12} | {issues_cnt:<15} | {tot_days:<12.1f} | {avg_days:<15.1f}"
        )


if __name__ == "__main__":
    main()
