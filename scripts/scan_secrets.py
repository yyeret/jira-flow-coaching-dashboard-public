"""Run a checksum-pinned Gitleaks release on macOS, Linux, or Windows."""

import argparse
import hashlib
import io
from pathlib import Path
import platform
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

VERSION = "8.30.1"
CHECKSUMS = {
    "darwin_arm64.tar.gz": "b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5",
    "darwin_x64.tar.gz": "dfe101a4db2255fc85120ac7f3d25e4342c3c20cf749f2c20a18081af1952709",
    "linux_arm64.tar.gz": "e4a487ee7ccd7d3a7f7ec08657610aa3606637dab924210b3aee62570fb4b080",
    "linux_x64.tar.gz": "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb",
    "windows_x64.zip": "d29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e",
}
ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args()
    system = platform.system().lower()
    arch = "arm64" if platform.machine().lower() in {"arm64", "aarch64"} else "x64"
    suffix = f"{system}_{arch}.{'zip' if system == 'windows' else 'tar.gz'}"
    if suffix not in CHECKSUMS:
        parser.error(f"Unsupported platform: {suffix}")
    name = f"gitleaks_{VERSION}_{suffix}"
    url = f"https://github.com/gitleaks/gitleaks/releases/download/v{VERSION}/{name}"
    with urllib.request.urlopen(url, timeout=60) as response:
        archive = response.read()
    if hashlib.sha256(archive).hexdigest() != CHECKSUMS[suffix]:
        raise RuntimeError("Gitleaks checksum mismatch")
    binary_name = "gitleaks.exe" if system == "windows" else "gitleaks"
    if system == "windows":
        with zipfile.ZipFile(io.BytesIO(archive)) as package:
            binary = package.read(binary_name)
    else:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as package:
            binary = package.extractfile(binary_name).read()
    tools = ROOT / ".tools"
    tools.mkdir(exist_ok=True)
    executable = tools / binary_name
    executable.write_bytes(binary)
    executable.chmod(0o700)
    command = [str(executable), "git" if args.history else "dir", "--redact"]
    if args.history:
        command.append("--log-opts=--all")
    else:
        # Scan the release bundle, not node_modules or private ignored exports.
        command.append(str(ROOT / "dist"))
    return subprocess.call(command, cwd=ROOT)


if __name__ == "__main__":
    sys.exit(main())
