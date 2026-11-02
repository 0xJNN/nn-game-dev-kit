"""Small independent gate: reject empty, duplicate, contradictory, or failed checks."""
import argparse
import json
from pathlib import Path


def verify(path: Path, minimum: int) -> None:
    report = json.loads(path.read_text(encoding="utf-8"))
    checks = report.get("checks", [])
    if report.get("status") != "passed" or not isinstance(checks, list) or len(checks) < minimum:
        raise ValueError("Missing passing gold-path evidence")
    names = []
    for check in checks:
        if not isinstance(check, dict) or check.get("passed") is not True or not check.get("name"):
            raise ValueError("Every check must have a name and explicitly pass")
        names.append(check["name"])
    if len(set(names)) != len(names):
        raise ValueError("Duplicate checks are not independent coverage")
    if report.get("human_approval") != "pending":
        raise ValueError("Automated fixtures cannot grant human acceptance")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--min-checks", type=int, default=1)
    args = parser.parse_args()
    try:
        verify(args.report, args.min_checks)
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(1, f"Evidence rejected: {exc}\n")
    print("Evidence verified; human approval pending")
