#!/usr/bin/env python3
"""Opt-in local Training v3 integration. Native work always needs --execute.

No implicit engine launch, reuse of attempts, asset overwrite, raw-log output or
v2 stop fallback. A timeout remains unknown, even if the owned child was reaped.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pipeline.common import StudioError, atomic_json, load_json, resource_lock, utc_now

TASK = "hero-training-v3-implementation-2026-11-05"
CHECKPOINT = ROOT / ".studio/evidence" / (TASK + ".json")
EVIDENCE = ROOT / ".studio/evidence"
FRONTEND = "/Game/System/FrontEnd/Maps/L_LyraFrontEnd"
PENDING = {"reserved", "running_unknown", "outcome_unknown"}
PLAY_ID = re.compile(r"play-v3-[0-9a-f]{12}")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(path):
    return {p.relative_to(path).as_posix(): digest(p) for p in path.rglob("*") if p.is_file()}


def load_manager():
    spec = importlib.util.spec_from_file_location("owned_training_manager", Path(__file__).with_name("manage.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_preservation(checkpoint, manager):
    current = inventory(manager.STAGE / "Content")
    before = checkpoint["content_before_sha256"]
    if any(current.get(name) != value for name, value in before.items()):
        raise StudioError("Existing v1/v2 assets changed; preserve and review")
    if any(not name.startswith("TrainingV3/") for name in set(current) - set(before)):
        raise StudioError("Unrecognized asset addition outside TrainingV3")
    for name, value in checkpoint["source_before_sha256"].items():
        if name == "NovanodeHeroes.uplugin" or name.endswith("/NovanodeHeroes.Build.cs"):
            continue  # Explicit additive dependency changes are bound by the new build manifest.
        if digest(manager.SOURCE / name) != value:
            raise StudioError("Original v1/v2 source changed outside the approved scope")
    for group in ("prior_journal_sha256", "frozen_predecessor_sha256"):
        for name, value in checkpoint[group].items():
            if name == ".studio/evidence/hero-sandbox-install.json":
                continue  # Its exact prior bytes/module were archived before the explicit build transition.
            if digest(ROOT / name) != value:
                raise StudioError("Frozen predecessor changed; preserve and review")
    for name, value in checkpoint.get("implementation_frozen_sha256", {}).items():
        if digest(ROOT / name) != value:
            raise StudioError("Frozen integration phase changed; checkpoint before continuing")
    return current


def journals():
    paths = sorted(EVIDENCE.glob("hero-sandbox-job-*.json"))
    paths += sorted(EVIDENCE.glob("hero-training-v3-*-job-*.json"))
    if len(paths) > 256:
        raise StudioError("Native inventory exceeds this bounded integration's limits")
    return [(path, load_json(path)) for path in paths]


def eligible(rows, operation):
    if any(row.get("state") in PENDING for _, row in rows):
        raise StudioError("Pending native outcome/owner; reconcile, never resubmit")
    current = [row for _, row in rows if row.get("task") == TASK]
    if operation != "play-v3" and any(row.get("operation") == operation for row in current):
        raise StudioError("This frozen phase already attempted that operation; checkpoint and stop")
    if operation != "play-v3" and len([row for row in current if row.get("operation") != "play-v3"]) >= 3:
        raise StudioError("This integration's native operation cap is exhausted")


def summarize(path, build=False):
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 32 * 1024 * 1024:
        raise StudioError("Missing/oversized native output; no success classification")
    text = path.read_text(errors="replace")
    result = {
        "sha256": digest(path),
        "fatal_count": len(re.findall(r"Fatal error:|Critical error:|Assertion failed:", text, re.I)),
        "error_severity_count": len(re.findall(r"Log\w+:\s*Error:", text)),
        "normal_exit_marker": bool(re.search(r"LogExit:\s*(?:Display:\s*)?Exiting\.", text)),
    }
    if build:
        # Only lines originating in our new authored translation units, never
        # surrounding compiler excerpts from sample/engine headers.
        result["owned_diagnostics"] = [line for line in text.splitlines() if re.search(
            r"HeroTraining(?:UI|Combat|Editor|Flow)?\.(?:cpp|h)(?:\(\d|:\d).*?(?:error|warning):", line)][:32]
    return result


def verify_current(manager, rows, assets=False):
    accepted = load_json(EVIDENCE / "hero-sandbox-install.json")["sha256"]
    manager.verify_staged_code_paths(accepted)
    if inventory(manager.SOURCE) != accepted or any(digest(manager.STAGE / name) != value for name, value in accepted.items()):
        raise StudioError("Source/stage differs from the accepted build; no stale binary launch")
    build = manager.verify_build_identity(accepted, manager.STAGE / "Binaries/Linux/libUnrealEditor-NovanodeHeroes.so", [row for _, row in rows])
    preparation = None
    if assets:
        current = inventory(manager.STAGE / "Content")
        candidates = [row for _, row in rows if row.get("operation") == "validate-v3" and row.get("state") == "completed"
                      and row.get("preparation", {}).get("generated_sha256") == current]
        if len(candidates) != 1:
            raise StudioError("One exact, error-free v3 asset validation is required")
        preparation = candidates[0]["job_id"]
    return accepted, build, preparation


def launch_arguments(manager, startup):
    common = [arg + ",[/Script/PythonScriptPlugin.PythonScriptPluginSettings]:bRemoteExecution=False"
              if arg.startswith("-ini:Engine:") else arg for arg in startup.common_arguments()]
    return [str(manager.ENGINE / "Engine/Binaries/Linux/UnrealEditor"), str(manager.WORK / "Lyra.uproject"), FRONTEND,
            *common, "-game", "-DisablePython", "-HeroTrainingV3", "-windowed", "-ResX=1280", "-ResY=720"]


def run(operation, execute=False):
    if not execute:
        return {"state": "preview", "operation": operation, "engine_started": False,
                "command": ["python3", "projects/hero-sandbox/hero_training.py", operation, "--execute"],
                "human_approval": "pending"}
    manager = load_manager()
    import lyra_startup as startup
    import hero_training_v3_compatibility_complete_run as supervisor
    with resource_lock("integrator", ROOT), resource_lock("unreal-editor", ROOT):
        checkpoint = load_json(CHECKPOINT)
        if not checkpoint.get("implementation_frozen_sha256"):
            raise StudioError("Integration must be checkpointed and frozen before native execution")
        rows = journals()
        eligible(rows, operation)
        manager.baseline()
        content_before = check_preservation(checkpoint, manager)
        version = load_json(manager.ENGINE / "Engine/Build/Build.version")
        if [version.get(key) for key in ("MajorVersion", "MinorVersion", "PatchVersion")] != [5, 8, 4]:
            raise StudioError("Approved Unreal 5.8.4 identity differs")
        gpu = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10)
        if gpu.returncode or not gpu.stdout.strip() or int(gpu.stdout.splitlines()[0]) < 8192:
            raise StudioError("Insufficient confirmed VRAM; never stop user services")
        if operation == "build":
            source = manager.sync()
            build = preparation = None
        else:
            source, build, preparation = verify_current(manager, rows, assets=operation == "play-v3")
        if operation == "prepare-v3" and any(name.startswith("TrainingV3/") for name in content_before):
            raise StudioError("V3 assets already exist; preserve partial/prepared work, do not overwrite")
        if operation == "validate-v3":
            candidates = [row for _, row in rows if row.get("operation") == "prepare-v3" and row.get("state") == "completed"
                          and row.get("preparation", {}).get("generated_sha256") == content_before]
            if len(candidates) != 1:
                raise StudioError("Fresh exact preparation identity required before read-only validation")
        job = operation + "-" + uuid.uuid4().hex[:12]
        folder = ROOT / ".studio/builds/hero-training-v3-implementation" / job
        folder.mkdir(parents=True, exist_ok=False)
        journal = EVIDENCE / f"hero-sandbox-job-{job}.json"
        log, console = folder / "engine.log", folder / "console.log"
        if operation == "build":
            argv = [str(manager.ENGINE / "Engine/Build/BatchFiles/Linux/Build.sh"), "LyraEditor", "Linux", "Development",
                    "-Project=" + str(manager.WORK / "Lyra.uproject"), "-WaitMutex", "-NoHotReload", "-MaxParallelActions=6"]
        elif operation == "play-v3":
            if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
                raise StudioError("No graphical session")
            argv = launch_arguments(manager, startup) + ["-AbsLog=" + str(log)]
        else:
            script = "prepare_training.py" if operation == "prepare-v3" else "validate_training.py"
            common = [arg + ",[/Script/PythonScriptPlugin.PythonScriptPluginSettings]:bRemoteExecution=False"
                      if arg.startswith("-ini:Engine:") else arg for arg in startup.common_arguments()]
            argv = [str(manager.ENGINE / "Engine/Binaries/Linux/UnrealEditor-Cmd"), str(manager.WORK / "Lyra.uproject"),
                    *common, "-unattended", "-NullRHI", "-nosound", "-run=pythonscript",
                    "-EnablePlugins=PythonScriptPlugin,EditorScriptingUtilities,IKRig,NovanodeHeroes",
                    "-script=" + str(Path(__file__).with_name(script)), "-AbsLog=" + str(log)]
        record = {"task": TASK, "job_id": job, "operation": operation, "state": "reserved", "started_at": utc_now(),
                  "command": argv, "source_sha256": source, "source_build": build, "prepared_assets": preparation,
                  "human_approval": "pending", "runtime_verified": False, "visual_verified": False,
                  "engine_version_sha256": digest(manager.ENGINE / "Engine/Build/Build.version")}
        atomic_json(journal, record)
        env = startup.environment()
        env["NN_HERO_TRAINING_DIR"] = str(folder)
        try:
            if operation == "play-v3":
                # Interactive operation is never called by this task. The original
                # launcher alone waits/records exit; stop sends one identity-bound SIGINT.
                with console.open("xb") as output:
                    child = subprocess.Popen(argv, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                             stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
                    record.update(state="running_unknown", **manager.identity(child))
                    atomic_json(journal, record)
                    print(json.dumps({"job_id": job, "pid": child.pid, "operation": operation}), flush=True)
                    code = child.wait()
                record.update(exit_code=code, process_exit_observed=True, finished_at=utc_now(), process={"reason": "completed", "exit_code": code})
                atomic_json(journal, record)
            else:
                supervisor.run_owned(argv, ROOT, env, console, record, journal, timeout=900, max_bytes=8_000_000)
            result = record["process"]
            if result["reason"] != "completed":
                record.update(state="outcome_unknown", reconciliation_required=True)
            else:
                record["summary"] = summarize(console if operation == "build" else log, build=operation == "build")
                check_preservation(checkpoint, manager)
                record["preservation"] = manager.baseline()
                ok = type(record.get("exit_code")) is int and record["exit_code"] == 0 and record["summary"]["fatal_count"] == 0
                if operation != "build":
                    ok = ok and record["summary"]["error_severity_count"] == 0 and record["summary"]["normal_exit_marker"] is True
                if operation == "build" and ok:
                    record["native_module_sha256"] = digest(manager.STAGE / "Binaries/Linux/libUnrealEditor-NovanodeHeroes.so")
                if operation in ("prepare-v3", "validate-v3"):
                    receipt = folder / ("prepare.json" if operation == "prepare-v3" else "validation.json")
                    record["preparation"] = load_json(receipt) if receipt.is_file() else {"state": "missing"}
                    ok = ok and record["preparation"].get("state") == "prepared"
                    if operation == "validate-v3":
                        record["preparation"].update(baseline_job_id=checkpoint["previous_preparation"],
                                                      pre_existing_sha256=checkpoint["content_before_sha256"])
                        ok = ok and inventory(manager.STAGE / "Content") == content_before
                record["state"] = "completed" if ok else "blocked"
            atomic_json(journal, record)
            safe = {key: value for key, value in record.items() if key not in ("command", "source_sha256", "preparation")}
            if "preparation" in record:
                safe["preparation"] = {key: value for key, value in record["preparation"].items()
                                       if key not in ("generated_sha256", "pre_existing_sha256")}
            return safe
        except (Exception, KeyboardInterrupt) as exc:
            record.update(state="blocked" if record.get("process_exit_observed") and record.get("process", {}).get("reason") == "completed"
                          else "outcome_unknown", error_type=type(exc).__name__)
            atomic_json(journal, record)
            raise


def stop_v3(job_id=None, timeout=20, dry_run=False):
    """Separate v3 identity policy; only reuse the tested generic pidfd transport."""
    from pipeline import hero_stop as transport
    if type(timeout) is not int or not 1 <= timeout <= 60:
        raise StudioError("Stop timeout must be 1..60 seconds")
    if job_id is not None and not PLAY_ID.fullmatch(job_id):
        raise StudioError("Stop requires a play-v3-<12 hex> ID; no v2/editor/build fallback")
    def target():
        paths = [EVIDENCE / f"hero-sandbox-job-{job_id}.json"] if job_id else sorted(EVIDENCE.glob("hero-sandbox-job-play-v3-*.json"))
        if len(paths) > 128:
            raise StudioError("Stop inventory exceeds limits")
        pending = []
        for path in paths:
            row = transport._read(ROOT, path)
            name = row.get("job_id", "")
            if not isinstance(name, str) or not PLAY_ID.fullmatch(name) or row.get("operation") != "play-v3" or path.name != f"hero-sandbox-job-{name}.json":
                raise StudioError("Untrusted v3 play identity")
            if row.get("state") not in PENDING | {"completed", "blocked"}:
                raise StudioError("Unknown v3 lifecycle; reconcile")
            if row.get("state") in PENDING: pending.append((path, row))
        if len(pending) > 1:
            raise StudioError("Ambiguous v3 sessions; select one --job-id")
        return pending[0] if pending else None
    def validate(row):
        manager = load_manager()
        pid, ticks, command = row.get("pid"), row.get("process_start_ticks"), row.get("command")
        if type(pid) is not int or pid <= 1 or not isinstance(ticks, str) or not ticks.isdecimal() or not isinstance(command, list):
            raise StudioError("Incomplete v3 process identity; reconcile")
        executable = manager.ENGINE / "Engine/Binaries/Linux/UnrealEditor"
        current = transport._proc(pid, executable, ticks)
        if current["argv"] != command or command[:3] != [str(executable), str(manager.WORK / "Lyra.uproject"), FRONTEND] or current["lifecycle"] == "Z":
            raise StudioError("V3 process argv/project/frontend differs; no signal")
        if "-HeroTrainingV3" not in command or "-game" not in command:
            raise StudioError("Missing explicit v3 session identity")
        boot = int(next(line.split()[1] for line in Path('/proc/stat').read_text().splitlines() if line.startswith('btime ')))
        started = datetime.fromisoformat(row["started_at"])
        if started.tzinfo is None or abs(boot + int(ticks) / os.sysconf('SC_CLK_TCK') - started.timestamp()) > 10:
            raise StudioError("V3 boot/start identity differs")
        parent = transport._proc(current["parent_pid"])
        launchers = {str(ROOT / "projects/hero-sandbox/hero_training.py"), "projects/hero-sandbox/hero_training.py"}
        if parent["uid"] != os.getuid() or parent["lifecycle"] == "Z" or int(parent["ticks"]) > int(ticks) or not launchers.intersection(parent["argv"]) or "play-v3" not in parent["argv"] or "--execute" not in parent["argv"]:
            raise StudioError("Original v3 supervisor unavailable; close normally/reconcile")
        bit = 1 << (signal.SIGINT - 1)
        if not current["caught"] & bit or current["ignored"] & bit:
            raise StudioError("No caught SIGINT handler; close the game normally")
    selected = target()
    if selected is None:
        return {"state": "not_running", "signal_sent": False}
    if dry_run:
        validate(selected[1])
        return {"state": "dry_run", "job_id": selected[1]["job_id"], "signal_sent": False, "read_only": True}
    with resource_lock("hero-training-v3-stop", ROOT):
        selected = target()
        if selected is None: return {"state": "not_running", "signal_sent": False}
        path, row = selected
        for _, previous in transport._records(ROOT, "hero-training-v3-stop-*.json"):
            if previous.get("job_id") == row["job_id"] and previous.get("state") != "stopped":
                raise StudioError("Previous v3 stop unresolved; no second signal")
        process = transport.PidfdProcess(row["pid"])
        receipt = None
        result = None
        try:
            validate(row)
            if process.exited(): raise StudioError("V3 process exited during validation; reconcile")
            receipt = EVIDENCE / ("hero-training-v3-stop-" + uuid.uuid4().hex[:12] + ".json")
            result = {"state": "reserved", "job_id": row["job_id"], "pid": row["pid"], "started_at": utc_now(),
                      "signal_sent": False, "native_success_verified": False, "human_approval": "pending"}
            atomic_json(receipt, result)
            current = transport._read(ROOT, path)
            if not transport._same_identity(row, current) or current.get("state") not in PENDING:
                raise StudioError("V3 lifecycle changed; no signal")
            validate(row)
            result.update(state="requesting_unknown", signal_sent=None)
            atomic_json(receipt, result)
            process.request_exit()
            result.update(state="waiting_for_launcher", signal_sent=True)
            atomic_json(receipt, result)
            result.update(transport._wait(ROOT, path, row, process, time.monotonic() + timeout))
            result["finished_at"] = utc_now()
            atomic_json(receipt, result)
            return result
        except (Exception, KeyboardInterrupt):
            if result is not None:
                result.update(state="outcome_unknown", reconciliation_required=True)
                atomic_json(receipt, result)
            raise
        finally:
            process.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build", "prepare-v3", "validate-v3", "play-v3", "stop"))
    parser.add_argument("--execute", action="store_true", help="Explicitly perform the selected native operation")
    parser.add_argument("--job-id")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.operation != "stop" and (args.job_id is not None or args.timeout != 20 or args.dry_run):
        parser.error("--job-id, --timeout and --dry-run are stop-only")
    if args.operation == "stop" and not (args.execute or args.dry_run):
        result = {"state": "preview", "operation": "stop", "signal_sent": False, "execute_required": True}
    else:
        result = stop_v3(args.job_id, args.timeout, args.dry_run) if args.operation == "stop" else run(args.operation, args.execute)
    print(json.dumps(result, indent=2))
    return 0 if result["state"] in ("preview", "completed", "stopped", "not_running", "dry_run") else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Exception, KeyboardInterrupt) as exc:
        print(json.dumps({"state": "stopped_preserve_and_review", "error_type": type(exc).__name__}))
        raise SystemExit(1)
