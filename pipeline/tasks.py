from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import uuid
from contextlib import nullcontext
from pathlib import Path

from .common import (
    ROOT, StudioError, atomic_json, config, load_json, money, project_path,
    resource_lock, utc_now,
)
from .process import run_process

IGNORED = {".git", ".studio", ".godot", ".venv", ".ruff_cache", "__pycache__", "artifacts",
           "Binaries", "Intermediate", "Saved", "DerivedDataCache", ".vs"}
TEXT_TYPES = {".md", ".py", ".gd", ".tscn", ".cfg", ".toml", ".json", ".txt",
              ".cpp", ".h", ".cs", ".ini", ".uproject"}


def read_contract(path: Path, root: Path = ROOT) -> dict:
    task = load_json(path)
    required = {"id", "goal", "inputs", "allowed_writes", "acceptance", "limits",
                "steps", "verification"}
    if not isinstance(task, dict) or set(task) - required - {"resource"} or required - set(task):
        raise StudioError(f"Task requires exactly {sorted(required)} plus optional resource")
    if not isinstance(task["id"], str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", task["id"]):
        raise StudioError("Task ID must be lowercase letters, numbers, and hyphens (1..64)")
    if not isinstance(task["goal"], str) or not task["goal"].strip():
        raise StudioError("Task goal cannot be empty")
    for field in ("inputs", "allowed_writes", "acceptance"):
        if not isinstance(task[field], list) or not all(
            isinstance(item, str) and item.strip() for item in task[field]
        ):
            raise StudioError(f"{field} must be a list of nonempty strings")
    if not task["acceptance"]:
        raise StudioError("Task requires explicit acceptance criteria")
    for value in task["inputs"] + task["allowed_writes"]:
        path_in_project = project_path(value, root)
        relative = path_in_project.relative_to(root.resolve())
        if relative == Path(".") or any(part in IGNORED for part in relative.parts):
            raise StudioError(f"Protected or overly broad task path: {value}")
        if any(part.startswith(".env") for part in relative.parts):
            raise StudioError("Environment/credential files cannot be task context or outputs")
    limits = task["limits"]
    if not isinstance(limits, dict) or set(limits) != {
        "deadline_seconds", "command_timeout_seconds", "max_attempts", "budget_usd"
    }:
        raise StudioError("Task limits require deadline, command_timeout, max_attempts, budget_usd")
    for key, lower, upper in (
        ("deadline_seconds", 1, 3600), ("command_timeout_seconds", 1, 3600),
        ("max_attempts", 1, 3),
    ):
        if type(limits[key]) is not int or not lower <= limits[key] <= upper:
            raise StudioError(f"{key} must be an integer in {lower}..{upper}")
    if limits["command_timeout_seconds"] > limits["deadline_seconds"]:
        raise StudioError("Command timeout exceeds task deadline")
    if money(limits["budget_usd"]) > money(config(root)["budgets"]["per_task_usd"]):
        raise StudioError("Task budget exceeds studio per-task cap")
    for field in ("steps", "verification"):
        if not isinstance(task[field], list) or not task[field]:
            raise StudioError(f"Task requires at least one {field} command")
        for step in task[field]:
            if not isinstance(step, dict) or set(step) != {"name", "argv"}:
                raise StudioError("Each command requires exactly name and argv")
            if not isinstance(step["name"], str) or not step["name"].strip():
                raise StudioError("Each command needs a name")
            if not isinstance(step["argv"], list) or not step["argv"] or not all(
                isinstance(arg, str) and arg and "\0" not in arg for arg in step["argv"]
            ):
                raise StudioError("argv must be a nonempty list of nonempty strings")
    if "resource" in task and not re.fullmatch(r"[a-z0-9-]{1,64}", str(task["resource"])):
        raise StudioError("Invalid shared resource name")
    return task


def task_context(task: dict, root: Path = ROOT) -> str:
    cap = config(root)["context"]["max_characters"]
    header = (
        "Complete only this contract. Do not launch helper agents without approval.\n"
        "Allowed writes are a review boundary, NOT an OS sandbox. Never access secrets.\n"
        "Use the jobs ledger before any approved paid call. Stop at acceptance or limits.\n"
        "Return evidence paths and unresolved defects; human approval remains pending.\n\n"
        + json.dumps(task, indent=2) + "\n"
    )
    if len(header) > cap:
        raise StudioError("Contract alone exceeds the context cap")
    chunks = [header]
    used = len(header)
    for name in task["inputs"]:
        path = project_path(name, root)
        if not path.is_file() or path.suffix not in TEXT_TYPES:
            raise StudioError(f"Context input must be an explicit supported text file: {name}")
        # Reject, rather than silently truncating essential requirements.
        if path.stat().st_size > cap * 4:
            raise StudioError(f"Context input too large: {name}; narrow the contract")
        block = f"\n--- {name} ---\n{path.read_text(encoding='utf-8')}\n"
        used += len(block)
        if used > cap:
            raise StudioError("Inputs exceed context cap; narrow inputs instead of loading everything")
        chunks.append(block)
    return "".join(chunks)


def snapshot(root: Path) -> dict[str, str]:
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        base = Path(directory)
        # Track symlink identity without reading targets outside the project.
        for name in list(dirs):
            path = base / name
            if name in IGNORED:
                dirs.remove(name)
            elif path.is_symlink():
                result[path.relative_to(root).as_posix()] = "link:" + os.readlink(path)
                dirs.remove(name)
        for name in files:
            path = base / name
            if name.endswith((".pyc", ".pyo")):
                continue
            if path.is_symlink():
                digest = "link:" + os.readlink(path)
            else:
                with path.open("rb") as stream:
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
            result[path.relative_to(root).as_posix()] = digest
    return result


def unexpected_writes(before: dict, after: dict, allowed: list[str]) -> list[str]:
    roots = [Path(item) for item in allowed]
    changed = sorted(key for key in before.keys() | after.keys() if before.get(key) != after.get(key))
    return [key for key in changed if not any(Path(key).is_relative_to(item) for item in roots)]


def run_task(contract: Path, execute=False, root: Path = ROOT) -> dict:
    task = read_contract(contract, root)
    if not execute:
        return {"status": "dry_run", "task": task,
                "notice": "Review argv before --execute. Commands run with your user's privileges."}
    run_id = f"{task['id']}-{uuid.uuid4().hex[:12]}"
    evidence = root / ".studio/runs" / run_id
    evidence.mkdir(parents=True)
    (evidence / "scratch").mkdir()
    atomic_json(evidence / "contract.json", task)
    result = {
        "run_id": run_id, "task_id": task["id"], "started_at": utc_now(),
        "status": "running", "human_approval": "pending", "commands": [],
        "budget_scope": "ledger reservations only; arbitrary subprocess billing is not observable",
    }
    report = evidence / "report.json"
    atomic_json(report, result)
    env = {key: os.environ[key] for key in (
        "PATH", "HOME", "LANG", "LC_ALL", "DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR",
        "GODOT_BIN", "BLENDER_BIN", "UE_ROOT", "DYLD_LIBRARY_PATH", "LD_LIBRARY_PATH",
    ) if key in os.environ}
    env.update({
        "TMPDIR": str(evidence / "scratch"), "PYTHONUNBUFFERED": "1",
        "NOVANODE_TASK_ID": task["id"], "NOVANODE_TASK_BUDGET_USD": str(task["limits"]["budget_usd"]),
        "NOVANODE_EVIDENCE": str(evidence),
    })
    substitutions = {"{python}": sys.executable, "{root}": str(root), "{evidence}": str(evidence)}
    started = time.monotonic()
    baseline = snapshot(root)
    lock = resource_lock(task["resource"], root) if task.get("resource") else nullcontext()
    try:
        with lock:
            for attempt in range(1, task["limits"]["max_attempts"] + 1):
                passed = True
                for phase in ("steps", "verification"):
                    for step in task[phase]:
                        remaining = task["limits"]["deadline_seconds"] - (time.monotonic() - started)
                        argv = list(step["argv"])
                        for index, arg in enumerate(argv):
                            for token, value in substitutions.items():
                                arg = arg.replace(token, value)
                            argv[index] = arg
                        record = {"attempt": attempt, "phase": phase, "name": step["name"], "argv": argv}
                        result["commands"].append(record)
                        atomic_json(report, result)
                        record.update(run_process(
                            argv, root, min(remaining, task["limits"]["command_timeout_seconds"]),
                            evidence / f"command-{len(result['commands']):02}.log", env,
                        ))
                        unexpected = unexpected_writes(baseline, snapshot(root), task["allowed_writes"])
                        if unexpected:
                            result.update(status="write_boundary_violated", unexpected_writes=unexpected)
                            return result
                        atomic_json(report, result)
                        if record["exit_code"] != 0 or record["reason"] != "completed":
                            passed = False
                            break
                    if not passed:
                        break
                if passed:
                    result["status"] = "machine_verified"
                    break
                if time.monotonic() - started >= task["limits"]["deadline_seconds"]:
                    result["status"] = "deadline_exceeded"
                    break
            else:
                result["status"] = "attempts_exhausted"
    except KeyboardInterrupt:
        result["status"] = "interrupted"
        raise
    except Exception as exc:
        result.update(status="error", error=str(exc))
        raise
    finally:
        result["finished_at"] = utc_now()
        result["seconds"] = round(time.monotonic() - started, 3)
        result["evidence"] = str(evidence)
        atomic_json(report, result)
    return result
