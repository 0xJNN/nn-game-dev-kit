"""Bounded, identity-bound stop control for one managed Linux play-v2 session.

Never edits native journals. The original launcher alone records its child's exit.
SIGINT is directed through a pidfd to a process with an installed handler, never
to the Python launcher/terminal group. No escalation or automatic resubmission.
"""
from __future__ import annotations

from datetime import datetime
import itertools
import os
from pathlib import Path
import re
import select
import signal
import time
import uuid

from .common import StudioError, atomic_json, load_json, project_path, resource_lock, utc_now

JOB = re.compile(r"play-v2-[0-9a-f]{12}")
MAX_RECORDS = 128
MAX_BYTES = 1_000_000
PENDING = {"reserved", "running_unknown"}
IDENTITY = ("job_id", "operation", "pid", "process_start_ticks", "started_at", "command")


def _path(root: Path, value: str) -> Path:
    path = project_path(value, root)
    candidate = root
    for part in Path(value).parts:
        candidate /= part
        if candidate.is_symlink():
            raise StudioError("Symlink in stop metadata; preserve and review")
    return path


def _read(root: Path, path: Path) -> dict:
    safe = _path(root, path.relative_to(root).as_posix())
    if not safe.is_file() or safe.stat().st_size > MAX_BYTES:
        raise StudioError("Missing/oversized stop metadata; preserve and review")
    try:
        row = load_json(safe)
    except RecursionError as exc:
        raise StudioError("Stop metadata nesting exceeds limits") from exc
    if not isinstance(row, dict):
        raise StudioError("Stop metadata must be an object")
    return row


def _records(root: Path, pattern: str) -> list[tuple[Path, dict]]:
    folder = _path(root, ".studio/evidence")
    paths = list(itertools.islice(folder.glob(pattern), MAX_RECORDS + 1))
    if len(paths) > MAX_RECORDS:
        raise StudioError("Stop inventory exceeds limits; no partial selection or signal")
    return [(path, _read(root, path)) for path in sorted(paths)]


def _target(root: Path, job_id: str | None):
    if job_id is not None:
        if not JOB.fullmatch(job_id):
            raise StudioError("--job-id must name a play-v2-<12 hex digits> job, not an editor/build")
        path = _path(root, f".studio/evidence/hero-sandbox-job-{job_id}.json")
        rows = [(path, _read(root, path))]
    else:
        rows = _records(root, "hero-sandbox-job-play-v2-*.json")
    pending = []
    for path, row in rows:
        name = row.get("job_id")
        if (not isinstance(name, str) or not JOB.fullmatch(name) or row.get("operation") != "play-v2"
                or path.name != f"hero-sandbox-job-{name}.json"):
            raise StudioError("Untrusted play journal identity; no process selected")
        state = row.get("state")
        if not isinstance(state, str) or state not in PENDING | {"completed", "blocked"}:
            raise StudioError("Unrecognized native lifecycle state; reconcile before stopping")
        if state in PENDING:
            pending.append((path, row))
    if len(pending) > 1:
        raise StudioError("Ambiguous play sessions; inspect journals and select exactly one --job-id")
    return pending[0] if pending else None


def _proc(pid: int, expected_executable: Path | None = None, expected_ticks: str | None = None) -> dict:
    """Exact PID only. Raw argv/status never leave this local validation path."""
    base = Path(f"/proc/{pid}")
    fields = (base / "stat").read_text().rsplit(")", 1)[1].split()
    status = dict(line.split(":", 1) for line in (base / "status").read_text().splitlines() if ":" in line)
    uid = int(status["Uid"].split()[0])
    executable = str((base / "exe").resolve(strict=True))
    if (uid != os.getuid() or (expected_ticks is not None and fields[19] != expected_ticks)
            or (expected_executable is not None and executable != str(expected_executable.resolve()))):
        raise StudioError("Process owner/executable/start differs; argv not inspected, no signal sent")
    argv = [arg.decode(errors="strict") for arg in (base / "cmdline").read_bytes().split(b"\0") if arg]
    return {"ticks": fields[19], "parent_pid": int(fields[1]), "lifecycle": fields[0],
            "uid": uid, "argv": argv, "executable": executable,
            "caught": int(status["SigCgt"].strip(), 16), "ignored": int(status["SigIgn"].strip(), 16)}


def _validate(row: dict, root: Path, executable: Path, project: Path, game_map: str) -> None:
    pid = row.get("pid")
    ticks = row.get("process_start_ticks")
    command = row.get("command")
    if (type(pid) is not int or pid <= 1 or not isinstance(ticks, str) or not ticks.isdecimal()
            or not isinstance(command, list) or not command or not all(isinstance(arg, str) for arg in command)):
        raise StudioError("Reserved/incomplete process identity; reconcile the journal, no signal sent")
    try:
        current = _proc(pid, expected_executable=executable, expected_ticks=ticks)
        if (current["uid"] != os.getuid() or current["ticks"] != ticks
                or current["executable"] != str(executable.resolve()) or current["argv"] != command
                or command[0] != str(executable) or str(project) not in command or game_map not in command
                or "-game" not in command or current["lifecycle"] == "Z"):
            raise StudioError("PID/user/executable/argv/project/map identity differs; no signal sent")
        boot = int(next(line.split()[1] for line in Path("/proc/stat").read_text().splitlines()
                        if line.startswith("btime ")))
        if not isinstance(row.get("started_at"), str):
            raise StudioError("Missing process start timestamp; no signal sent")
        started = datetime.fromisoformat(row["started_at"])
        if started.tzinfo is None or abs(boot + int(ticks) / os.sysconf("SC_CLK_TCK") - started.timestamp()) > 10:
            raise StudioError("Process start/boot identity differs; no signal sent")
        parent = _proc(current["parent_pid"])
        launcher_args = {str(root / "projects/hero-sandbox/manage.py"), "projects/hero-sandbox/manage.py"}
        if (parent["uid"] != os.getuid() or int(parent["ticks"]) > int(ticks)
                or parent["lifecycle"] == "Z" or "play-v2" not in parent["argv"]
                or not launcher_args.intersection(parent["argv"])):
            raise StudioError("Original play launcher identity unavailable; reconcile, no signal sent")
        bit = 1 << (signal.SIGINT - 1)
        if not current["caught"] & bit or current["ignored"] & bit:
            raise StudioError("Game has no caught SIGINT handler; close its window normally instead")
    except (OSError, ValueError, KeyError, IndexError, StopIteration) as exc:
        raise StudioError("Process/launcher identity unavailable; outcome unknown, reconcile before retrying") from exc


class PidfdProcess:
    def __init__(self, pid: int):
        if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
            raise StudioError("Safe stop needs Linux pidfd support; close the game window normally")
        try:
            self.fd = os.pidfd_open(pid, 0)
        except OSError as exc:
            raise StudioError("Cannot bind the recorded process with pidfd; no signal sent, reconcile") from exc

    def exited(self, timeout=0) -> bool:
        return bool(select.select([self.fd], [], [], max(0, timeout))[0])

    def request_exit(self):
        signal.pidfd_send_signal(self.fd, signal.SIGINT, None, 0)

    def close(self):
        os.close(self.fd)


def _same_identity(before: dict, after: dict) -> bool:
    return all(before.get(key) == after.get(key) for key in IDENTITY)


def _wait(root: Path, path: Path, original: dict, process, deadline: float) -> dict:
    exited = False
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return {"state": "outcome_unknown", "reason": "launcher_journal_timeout" if exited else "process_exit_timeout",
                    "reconciliation_required": True,
                    "action": "No escalation/retry. Inspect the stop receipt and original journal; close the game normally if still active."}
        exited = process.exited(min(0.1, remaining))
        row = _read(root, path)
        if not _same_identity(original, row):
            raise StudioError("Native journal identity changed while waiting; preserve and reconcile")
        if (exited and row.get("state") in ("completed", "blocked")
                and type(row.get("exit_code")) is int and isinstance(row.get("finished_at"), str)):
            try:
                if datetime.fromisoformat(row["finished_at"]).tzinfo is None:
                    raise ValueError("timezone required")
            except ValueError as exc:
                raise StudioError("Native exit timestamp invalid; preserve and reconcile") from exc
            summary = row.get("summary", {})
            return {"state": "stopped", "process_exited": True, "launcher_recorded_exit": True,
                    "native_job_state": row["state"], "native_exit_code": row["exit_code"],
                    "normal_exit_marker": isinstance(summary, dict) and summary.get("normal_exit_marker") is True,
                    "reconciliation_required": False, "native_success_verified": False}
        if exited:
            time.sleep(min(0.05, max(0, deadline - time.monotonic())))


def stop_session(root: Path, executable: Path, project: Path, game_map: str,
                 job_id: str | None = None, timeout: int = 20, dry_run=False) -> dict:
    if type(timeout) is not int or not 1 <= timeout <= 60:
        raise StudioError("--timeout must be an integer in 1..60 seconds")
    # Preview/no-op must not create locks, journals or receipt directories.
    if dry_run:
        target = _target(root, job_id)
        if target is None:
            return {"state": "not_running", "signal_sent": False, "read_only": True}
        _, row = target
        _validate(row, root, executable, project, game_map)
        return {"state": "dry_run", "job_id": row["job_id"], "pid": row["pid"],
                "request": "pidfd_SIGINT_to_game_only", "signal_sent": False, "read_only": True}
    if _target(root, job_id) is None:
        return {"state": "not_running", "signal_sent": False}
    _path(root, ".studio/locks/hero-play-stop.lock")
    with resource_lock("hero-play-stop", root):
        target = _target(root, job_id)
        if target is None:
            return {"state": "not_running", "signal_sent": False}
        path, row = target
        for stop_path, previous in _records(root, "hero-sandbox-stop-*.json"):
            if previous.get("job_id") == row["job_id"] and previous.get("state") != "stopped":
                raise StudioError("Earlier stop unresolved: " + stop_path.name + "; reconcile, do not send another signal")
        process = None
        receipt = None
        result = None
        try:
            # Pin the kernel process before validating /proc, closing the PID-reuse race.
            pid = row.get("pid")
            if type(pid) is not int or pid <= 1:
                raise StudioError("No recorded native PID; reconcile the reserved job")
            process = PidfdProcess(pid)
            _validate(row, root, executable, project, game_map)
            if process.exited():
                raise StudioError("Process exited during identity validation; reconcile, no signal sent")
            stop_id = "stop-" + uuid.uuid4().hex[:12]
            receipt = _path(root, f".studio/evidence/hero-sandbox-{stop_id}.json")
            if receipt.exists():
                raise StudioError("Stop receipt collision; preserve and review")
            result = {"stop_id": stop_id, "job_id": row["job_id"], "pid": pid,
                      "process_start_ticks": row["process_start_ticks"], "state": "reserved",
                      "started_at": utc_now(), "signal_sent": False, "native_success_verified": False,
                      "human_approval": "pending", "request": "pidfd_SIGINT_to_game_only"}
            atomic_json(receipt, result)
            deadline = time.monotonic() + timeout
            current = _read(root, path)
            if not _same_identity(row, current) or current.get("state") not in PENDING:
                raise StudioError("Native lifecycle changed before request; reconcile, no signal sent")
            _validate(row, root, executable, project, game_map)
            result.update(state="requesting_unknown", signal_sent=None, request_at=utc_now())
            atomic_json(receipt, result)
            if time.monotonic() >= deadline:
                raise StudioError("Stop deadline expired before the request; no signal sent, inspect the receipt")
            try:
                process.request_exit()
                result["signal_sent"] = True
            except ProcessLookupError:
                result["signal_sent"] = False  # Never signal a replacement PID.
            result.update(state="waiting_for_launcher")
            atomic_json(receipt, result)
            result.update(_wait(root, path, row, process, deadline))
            result["finished_at"] = utc_now()
            atomic_json(receipt, result)
            return {**result, "receipt": str(receipt.relative_to(root))}
        except (Exception, KeyboardInterrupt):
            if result is not None and receipt is not None:
                result.update(state="outcome_unknown", reconciliation_required=True, observed_at=utc_now())
                atomic_json(receipt, result)
            raise
        finally:
            if process is not None:
                process.close()
