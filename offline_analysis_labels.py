import csv
import argparse
from collections import defaultdict
import os


def main():
    parser = argparse.ArgumentParser(description="Analyze label correlation with flagged items")
    parser.add_argument(
        "--data-dir", required=True, help="Path to the directory containing the CSV exports"
    )
    parser.add_argument(
        "--min-issues",
        type=int,
        default=10,
        help="Minimum number of total issues for a label to be included (default: 10)",
    )
    parser.add_argument(
        "--sort",
        choices=["count", "flagged", "rate"],
        default="count",
        help="Field to sort by: count (total issues), flagged (flagged count), or rate (percentage flagged)",
    )
    parser.add_argument(
        "--limit", type=int, default=50, help="Maximum number of rows to display (default: 50)"
    )
    args = parser.parse_args()

    meta_path = os.path.join(args.data_dir, "issue_metadata.csv")
    flag_path = os.path.join(args.data_dir, "flag_history.csv")

    if not os.path.exists(meta_path) or not os.path.exists(flag_path):
        print("Could not find issue_metadata.csv or flag_history.csv in the specified directory.")
        return

    # 1. Track which issues were ever flagged
    flagged_issues = set()
    with open(flag_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("Action") == "Flagged":
                flagged_issues.add(row["Issue Key"])

    # 2. Count total issues per label, and flagged issues per label
    label_total = defaultdict(int)
    label_flagged = defaultdict(int)
    total_issues = 0
    total_flagged = len(flagged_issues)

    with open(meta_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = row.get("Issue Key")
            if not key:
                continue

            total_issues += 1
            labels_str = row.get("Labels", "")
            labels = [l.strip() for l in labels_str.split(",") if l.strip()]

            is_flagged = key in flagged_issues
            for label in labels:
                label_total[label] += 1
                if is_flagged:
                    label_flagged[label] += 1

    print(f"Total Issues Analyzed: {total_issues}")
    print(f"Total Flagged Issues: {total_flagged}")
    print(
        f"\n--- Label Analysis (Min Issues: {args.min_issues}, Sorted by: {args.sort}, Limit: {args.limit}) ---"
    )
    print(f"{'Label':<40} | {'Total Items':<15} | {'Flagged Items':<15} | {'% Flagged':<15}")
    print("-" * 90)

    # Filter labels by min issues
    filtered_labels = {l: c for l, c in label_total.items() if c >= args.min_issues}

    # Sort labels
    if args.sort == "count":
        sorted_labels = sorted(filtered_labels.items(), key=lambda x: x[1], reverse=True)
    elif args.sort == "flagged":
        sorted_labels = sorted(
            filtered_labels.items(), key=lambda x: label_flagged.get(x[0], 0), reverse=True
        )
    elif args.sort == "rate":
        sorted_labels = sorted(
            filtered_labels.items(),
            key=lambda x: (label_flagged.get(x[0], 0) / x[1]) if x[1] > 0 else 0,
            reverse=True,
        )

    for label, count in sorted_labels[: args.limit]:
        flagged_count = label_flagged.get(label, 0)
        pct = (flagged_count / count) * 100 if count > 0 else 0
        print(f"{label:<40} | {count:<15} | {flagged_count:<15} | {pct:.1f}%")


if __name__ == "__main__":
    main()
