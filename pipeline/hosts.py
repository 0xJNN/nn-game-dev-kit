"""Read-only two-host inventory. No service starts, inference, SSH, or readiness approval."""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import platform
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .common import ROOT, StudioError, utc_now

SCHEMA_VERSION = 1
ROLES = ("production", "inference")
MAX_SNAPSHOT_BYTES = 65536
TOOLS = ("nvidia-smi", "llama-server", "ollama", "opencode", "blender", "clang", "git")
GPU_FIELDS = "uuid,name,memory.total,memory.used,memory.free,driver_version"
PENDING_GATES = (
    "private_connection",
    "resource_ownership_and_live_vram",
    "exact_model_runtime_and_tool_transport",
    "representative_coding_benchmark",
    "current_unreal_build_and_runtime",
    "asset_import_and_packaged_slice",
    "request_accounting_and_premium_budget",
    "human_gameplay_and_visual_approval",
)


def _integer(value, minimum=0):
    return type(value) is int and value >= minimum


def parse_gpus(text: str) -> list[dict]:
    """Reject unsupported/partial metrics rather than inventing available VRAM."""
    if len(text.encode("utf-8")) > MAX_SNAPSHOT_BYTES:
        raise ValueError("GPU response too large")
    devices = []
    for row in csv.reader(io.StringIO(text), skipinitialspace=True):
        if len(row) != 6:
            raise ValueError("Unexpected GPU columns")
        uuid, name, total, used, free, driver = (value.strip() for value in row)
        total, used, free = int(total), int(used), int(free)
        if (not uuid.startswith("GPU-") or not name or driver in ("", "N/A")
                or total <= 0 or not 0 <= used <= total or not 0 <= free <= total
                or used + free > total):
            raise ValueError("Invalid GPU identity or memory")
        devices.append({"uuid": uuid, "name": name, "total_mib": total,
                        "used_mib": used, "free_mib": free, "driver_version": driver})
    if not devices or len({device["uuid"] for device in devices}) != len(devices):
        raise ValueError("Missing or duplicate GPUs")
    return devices


def probe_gpus(executable: str | None) -> dict:
    if executable is None:
        return {"status": "unknown", "reason": "nvidia_smi_not_found", "devices": []}
    try:
        result = subprocess.run(
            [executable, f"--query-gpu={GPU_FIELDS}", "--format=csv,noheader,nounits"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, timeout=5, check=False,
        )
        if result.returncode != 0:
            return {"status": "unknown", "reason": "nvidia_smi_nonzero_exit",
                    "exit_code": result.returncode, "devices": []}
        return {"status": "observed", "devices": parse_gpus(result.stdout)}
    except subprocess.TimeoutExpired:
        return {"status": "unknown", "reason": "nvidia_smi_timeout", "devices": []}
    except (OSError, ValueError):
        return {"status": "unknown", "reason": "nvidia_smi_unreadable", "devices": []}


def _proc_value(path: str, key: str) -> str | None:
    try:
        with Path(path).open(encoding="utf-8") as stream:
            for line in stream.read(2 * 1024 * 1024).splitlines():
                name, separator, value = line.partition(":")
                if separator and name.strip() == key:
                    return value.strip()
    except (OSError, UnicodeError):
        pass
    return None


def inventory(node: str, role: str, disk_path: Path = ROOT) -> dict:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}", node) or role not in ROLES:
        raise StudioError("Use a short node label and role production or inference")
    started = utc_now()
    try:
        release = platform.freedesktop_os_release()
    except OSError:
        release = {}
    ram = _proc_value("/proc/meminfo", "MemTotal")
    ram_match = re.fullmatch(r"(\d+)\s+kB", ram or "")
    try:
        disk_free = shutil.disk_usage(disk_path).free // (1024 * 1024)
    except OSError:
        disk_free = None
    tools = {name: shutil.which(name) for name in TOOLS}
    gpu = probe_gpus(tools["nvidia-smi"])
    return {
        "schema_version": SCHEMA_VERSION,
        "started_at": started,
        "captured_at": utc_now(),
        "node": node,
        "role": role,
        "hostname": platform.node(),
        "system": {
            "platform": platform.system(), "distribution": release.get("ID"),
            "distribution_version": release.get("VERSION_ID"), "kernel": platform.release(),
            "cpu_model": _proc_value("/proc/cpuinfo", "model name"),
            "logical_cpus": os.cpu_count(),
            "ram_total_mib": int(ram_match[1]) // 1024 if ram_match else None,
            "disk_path": str(disk_path.resolve()), "disk_free_mib": disk_free,
        },
        "tools_found_not_qualified": tools,
        "gpu": gpu,
        "scope": "inventory_only_not_a_resource_reservation",
        "pipeline_verified": False,
        "human_approval": "pending",
    }


def read_snapshot(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_SNAPSHOT_BYTES:
        raise StudioError("Snapshot must be a regular JSON file of at most 64 KiB")
    try:
        with path.open("rb") as stream:
            content = stream.read(MAX_SNAPSHOT_BYTES + 1)
        if len(content) > MAX_SNAPSHOT_BYTES:
            raise ValueError("Oversized snapshot")
        value = json.loads(content.decode("utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise StudioError("Cannot decode snapshot JSON") from exc
    if not isinstance(value, dict):
        raise StudioError("Snapshot must be a JSON object")
    return value


def compare(snapshots: list[dict], *, now: datetime | None = None) -> dict:
    """Check evidence completeness for the proposed pair, never qualify workloads."""
    now = now or datetime.now(timezone.utc)
    issues = []
    seen_nodes, seen_roles, seen_hosts, seen_gpus = set(), set(), set(), set()
    if len(snapshots) != 2:
        issues.append({"node": None, "code": "exactly_two_snapshots_required"})
    for index, snapshot in enumerate(snapshots):
        label = f"snapshot_{index + 1}"

        def issue(code):
            issues.append({"node": label, "code": code})

        if not isinstance(snapshot, dict):
            issue("invalid_snapshot")
            continue
        if type(snapshot.get("schema_version")) is not int or snapshot["schema_version"] != 1:
            issue("unsupported_schema")
            continue
        node = snapshot.get("node")
        if not isinstance(node, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}", node):
            issue("invalid_node")
        else:
            label = node
            if node in seen_nodes:
                issue("duplicate_node")
            seen_nodes.add(node)
        role = snapshot.get("role")
        if not isinstance(role, str) or role not in ROLES:
            issue("invalid_role")
        elif role in seen_roles:
            issue("duplicate_role")
        else:
            seen_roles.add(role)
        hostname = snapshot.get("hostname")
        if not isinstance(hostname, str) or not hostname.strip():
            issue("missing_hostname")
        elif hostname in seen_hosts:
            issue("same_hostname_review_required")
        else:
            seen_hosts.add(hostname)
        try:
            captured = datetime.fromisoformat(snapshot["captured_at"])
            if captured.utcoffset() is None:
                raise ValueError("Missing timezone")
            age = (now - captured).total_seconds()
            if age < -60 or age > 24 * 3600:
                issue("stale_or_future_snapshot")
        except (KeyError, ValueError, TypeError):
            issue("invalid_timestamp")
        system = snapshot.get("system")
        if not isinstance(system, dict):
            issue("missing_system")
        else:
            if system.get("platform") != "Linux":
                issue("linux_required")
            for field in ("distribution", "cpu_model"):
                if not isinstance(system.get(field), str) or not system[field].strip():
                    issue(f"missing_{field}")
            if not _integer(system.get("logical_cpus"), 1):
                issue("missing_logical_cpus")
            # Linux exposes slightly less than the installed 64 GiB.
            if not _integer(system.get("ram_total_mib"), 60 * 1024):
                issue("ram_below_baseline_or_unknown")
            if not _integer(system.get("disk_free_mib")):
                issue("disk_space_unknown")
        gpu = snapshot.get("gpu")
        if not isinstance(gpu, dict) or gpu.get("status") != "observed":
            issue("gpu_observation_unknown")
            continue
        devices = gpu.get("devices")
        if not isinstance(devices, list) or not devices:
            issue("missing_gpu_devices")
            continue
        baseline_found = False
        for device in devices:
            if not isinstance(device, dict):
                issue("invalid_gpu")
                continue
            uuid = device.get("uuid")
            if not isinstance(uuid, str) or not uuid.startswith("GPU-"):
                issue("missing_gpu_identity")
            elif uuid in seen_gpus:
                issue("duplicate_gpu_identity")
            else:
                seen_gpus.add(uuid)
            total, used, free = (device.get(key) for key in ("total_mib", "used_mib", "free_mib"))
            if (not _integer(total, 1) or not _integer(used) or not _integer(free)
                    or used + free > total):
                issue("gpu_memory_unknown_or_invalid")
                continue
            name = device.get("name")
            if isinstance(name, str) and "RTX 3090" in name and total >= 23 * 1024:
                baseline_found = True
            if (not isinstance(device.get("driver_version"), str)
                    or device["driver_version"].strip() in ("", "N/A")):
                issue("missing_gpu_driver")
        if not baseline_found:
            issue("rtx3090_24g_baseline_not_observed")
    if seen_roles != set(ROLES):
        issues.append({"node": None, "code": "production_and_inference_required"})
    return {
        "schema_version": SCHEMA_VERSION, "checked_at": now.isoformat(),
        "status": "inventory_complete" if not issues else "blocked",
        "issues": issues, "pending_gates": list(PENDING_GATES),
        "pipeline_verified": False, "human_approval": "pending",
        "note": "Snapshots are observations, not proof of connectivity or reserved GPU memory.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    collect = commands.add_parser("inventory", help="Print a local read-only JSON snapshot")
    collect.add_argument("--node", required=True)
    collect.add_argument("--role", choices=ROLES, required=True)
    collect.add_argument("--disk-path", type=Path, default=ROOT)
    pair = commands.add_parser("compare", help="Check two snapshots; does not contact either PC")
    pair.add_argument("snapshots", nargs=2, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "inventory":
            report = inventory(args.node, args.role, args.disk_path)
            code = 0
        else:
            report = compare([read_snapshot(path) for path in args.snapshots])
            code = 0 if report["status"] == "inventory_complete" else 1
        print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
        return code
    except (StudioError, OSError):
        print(json.dumps({"status": "error", "message": "Invalid or unreadable inventory input"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
