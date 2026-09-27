"""Run GUI tests in separate processes; retain logs even on a native crash."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-known-crash", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    artifacts = root / "artifacts"
    artifacts.mkdir(exist_ok=True)
    cases = [
        ("docking", []),
        ("video-static", ["--video", "--stationary"]),
    ]
    if args.include_known_crash:
        cases.append(("video-move", ["--video"]))
    results = []
    for name, flags in cases:
        env = os.environ.copy()
        env["QT_LOGGING_RULES"] = "qt.scenegraph.general=true"
        command = [sys.executable, "-u", str(root / "docking_probe.py"), "--self-test", *flags]
        try:
            result = subprocess.run(command, cwd=root, env=env, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=45)
            output, returncode = result.stdout, result.returncode
        except subprocess.TimeoutExpired as exc:
            output = exc.stdout or b""
            if isinstance(output, bytes):
                output = output.decode(errors="replace")
            returncode = 124
        (artifacts / f"{name}.log").write_text(output)
        results.append({"name": name, "returncode": returncode})
        print(f"{name}: exit={returncode}", flush=True)
    (artifacts / "suite.json").write_text(json.dumps(results, indent=2) + "\n")
    return int(any(item["returncode"] != 0 for item in results))


if __name__ == "__main__":
    raise SystemExit(main())
