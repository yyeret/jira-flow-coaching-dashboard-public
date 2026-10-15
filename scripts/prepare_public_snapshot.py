"""Export the reviewed working tree without private Git history or ignored files."""

import argparse
from pathlib import Path
import shutil
import sys

from check_public_tree import ROOT, check, release_files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    destination = args.output.resolve()
    if destination.exists() or destination == ROOT or ROOT in destination.parents:
        parser.error("Output must be a new directory outside the repository")
    if check():
        return 1
    destination.mkdir(parents=True)
    for name in release_files():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    print(f"Prepared source snapshot without .git: {destination}")
    print("No repository was created or published. Review ownership before licensing publicly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
