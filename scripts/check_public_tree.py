"""Check the prospective release tree without printing secret or customer values."""

import csv
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def release_files():
    result = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
    )
    return sorted({p for p in result.decode().split("\0") if p and (ROOT / p).is_file()})


def check():
    findings = []
    secrets = re.compile(
        r"AIza[0-9A-Za-z_-]{30,}|ATATT[0-9A-Za-z_=.-]{20,}|"
        r"gh[pousr]_[A-Za-z0-9]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    )
    for name in release_files():
        path = ROOT / name
        if path.is_symlink():
            findings.append((name, "symlink requires manual review"))
            continue
        if name.startswith(("batch_results_", ".playwright-cli/", "coverage/")) or name in {
            ".coverage",
            ".DS_Store",
        }:
            findings.append((name, "private or generated artifact"))
        if path.suffix == ".csv":
            if not name.startswith("sample_data/"):
                findings.append((name, "CSV outside synthetic sample directory"))
            else:
                with path.open(encoding="utf-8-sig", newline="") as source:
                    for row in csv.DictReader(source):
                        for field in ("Issue Key", "Source Issue Key", "Target Issue Key"):
                            key = row.get(field, "")
                            if key and not re.fullmatch(r"(?:FLOW|EPIC|FEAT)-[A-Z0-9-]+", key):
                                findings.append((name, "non-simulator issue key"))
                                break
        try:
            content = path.read_text(encoding="utf-8-sig")
        except UnicodeError:
            continue
        if secrets.search(content):
            findings.append((name, "credential-shaped content"))
        # A filesystem profile or real Jira hostname is not a secret, but should
        # not be accidentally distributed with a generic public tool.
        if re.search(r"/Users/[A-Za-z][^/\s]+/|[A-Z]:\\Users\\[^\\]+\\", content):
            findings.append((name, "personal absolute path"))
        hosts = re.findall(r"https://([a-zA-Z0-9-]+)\.atlassian\.net", content)
        if any(host not in {"your-domain", "mock-jira", "example"} for host in hosts):
            findings.append((name, "non-example Jira hostname"))
    for name, reason in findings:
        print(f"FAIL {name}: {reason}")
    print(f"Public tree: {len(release_files())} files checked; {len(findings)} findings")
    return bool(findings)


if __name__ == "__main__":
    sys.exit(check())
