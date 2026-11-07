#!/usr/bin/env python3
"""Frozen, local native-original-frontend gates. Preview unless explicitly executed."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("preserved_native_utilities", Path(__file__).with_name("native_training.py"))
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)
from pipeline.common import StudioError, atomic_json, load_json, resource_lock, utc_now
from pipeline.hero_play import command as manual_command

TASK = "hero-native-original-frontend-2026-11-07"
CHECKPOINT = ROOT / ".studio/evidence/hero-native-original-audited-start-2026-11-07.json"
BUILD = ROOT / ".studio/builds/hero-native-original"
RECIPE = Path(__file__).with_name("prepare_native_frontend.py")
INSTALL = ROOT / ".studio/evidence/hero-native-original-install.json"
PREFIX = "hero-native-original-job-"
CHANGES = {"Source/NovanodeTraining/Public/TrainingFlow.h", "Source/NovanodeTraining/Public/TrainingLobby.h",
           "Source/NovanodeTraining/Public/TrainingReflectionAdapter.h", "Source/NovanodeTraining/Private/TrainingLobby.cpp",
           "Source/NovanodeTraining/Private/TrainingMatchComponent.cpp", "Source/NovanodeTraining/Private/TrainingNativeFrontend.cpp"}


def phase_rows():
    return [load_json(p) for p in native.EVIDENCE.glob(PREFIX + "*.json")]


def audit(*, before=False):
    cp = load_json(CHECKPOINT)
    index = hashlib.sha256(subprocess.check_output(["git", "ls-files", "--stage"], cwd=ROOT)).hexdigest()
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    if index != cp["index_sha256"] or revision != cp["revision"]:
        raise StudioError("Revision/index drift; preserve external staging and checkpoint")
    for name, expected in cp["prior_journals"].items():
        if native.digest(ROOT / name) != expected:
            raise StudioError("Prior journal drift: " + name)
    if native.manifest(native.STAGE / "Content", generated=True) != cp["content"]:
        raise StudioError("One of the 13 preserved assets changed")
    if native.digest(native.STAGE / native.LOADER) != cp["loader_before"]:
        raise StudioError("Proven loader inventory changed")
    authored = native.manifest(native.SOURCE)
    expected = cp["plugin_before"] if before else authored
    if before:
        changed = {k for k in authored.keys() | expected.keys() if authored.get(k) != expected.get(k)}
        if changed != CHANGES or set(expected) - set(authored):
            raise StudioError("Changes are not exactly the bounded owned frontend source set")
        if native.digest(native.STAGE / native.MODULE) != cp["module_before"]:
            raise StudioError("Compiled parent identity drift")
    else:
        receipt = load_json(INSTALL)
        if receipt["source_sha256"] != authored:
            raise StudioError("Authored source differs from exact installed source receipt")
    if any(native.digest(native.STAGE / k) != h for k, h in expected.items()):
        raise StudioError("Installed owned source mismatch")
    startup, helper = native.helpers()
    if helper.active_editors():
        raise StudioError("Existing Unreal owner; close normally")
    base = load_json(native.BASELINE)
    if helper.source_inventory(native.WORK) != {**base["source_sha256"], **native.plugin_inventory(expected)}:
        raise StudioError("Original or owned installed source inventory drift")
    if helper.source_inventory(startup.repair.VAULT) != base["vault_sha256"]:
        raise StudioError("Original vault drift")
    if any(native.digest(native.WORK / k) != h for k, h in base["binary_sha256"].items()):
        raise StudioError("Original ELF drift")
    return {"original_sources": len(base["source_sha256"]), "original_modules": len(base["binary_sha256"]),
            "owned_assets_unchanged": len(cp["content"]), "index_preserved": True}


def command(operation, folder):
    if operation == "build":
        return native.command("build", folder)
    argv = manual_command(ROOT, native.ENGINE)
    argv[0] = str(native.ENGINE / "Engine/Binaries/Linux/UnrealEditor-Cmd")
    argv = [x for x in argv if x not in ("-game", "-fullscreen", "-DPCVars=r.FullScreenMode=1")]
    argv += ["-unattended", "-NullRHI", "-nosound", "-AbsLog=" + str(folder / "engine.log")]
    if operation == "verify":
        argv += ["-game", "-NovanodeTrainingProbe=" + str(folder / "result.json"),
                 "-NovanodeTrainingDiagnostics=" + str(folder / "initialization.jsonl")]
    else:
        argv = [x for x in argv if x != "-DisablePython"]
        argv += ["-run=pythonscript", "-script=" + str(RECIPE)]
    return argv


def verified_result(result):
    return (native.verified_loop_result(result) and result.get("native_frontend") is True and
            all(result.get(k) == 2 for k in ("native_menu_callbacks", "native_experience_callbacks", "native_host_callbacks")))


def run(operation):
    if os.environ.get("NOVANODE_TASK_ID") != TASK:
        raise StudioError("A new reviewed bounded task is required")
    with resource_lock("integrator", ROOT), resource_lock("unreal-editor", ROOT):
        native.ensure_no_pending()
        rows = phase_rows()
        if any(row["operation"] == operation for row in rows):
            raise StudioError("Phase already attempted; never blindly retry")
        preservation = audit(before=operation == "build")
        source = native.manifest(native.SOURCE)
        if operation != "build":
            prior = "build" if operation == "schema" else "schema"
            matches = [r for r in rows if r["operation"] == prior and r["state"] == "completed" and
                       r["source_sha256"] == source and r["module_sha256"] == native.digest(native.STAGE / native.MODULE)]
            if len(matches) != 1:
                raise StudioError("Missing source-exact prerequisite: " + prior)
        gpu = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, check=True, timeout=10)
        if int(gpu.stdout.splitlines()[0]) < 4096:
            raise StudioError("Insufficient VRAM; do not stop user services")
        if operation == "build":
            cp = load_json(CHECKPOINT)
            for name in CHANGES:
                target = native.STAGE / name
                if name not in cp["plugin_before"] and target.exists():
                    raise StudioError("Unexpected new installed source")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(native.SOURCE / name, target)
            atomic_json(INSTALL, {"source_sha256": source, "installed_at": utc_now(), "parent_checkpoint": str(CHECKPOINT)})
        job = operation + "-" + uuid.uuid4().hex[:12]
        folder = BUILD / job
        folder.mkdir(parents=True, exist_ok=False)
        path = native.EVIDENCE / (PREFIX + job + ".json")
        inputs = [Path(__file__), RECIPE, ROOT / "pipeline/hero_play.py", ROOT / "tests/test_native_frontend.py",
                  ROOT / "tests/test_hero_play.py", ROOT / "docs/HERO_SANDBOX.md", ROOT / f".studio/tasks/{TASK}.json"]
        argv = command(operation, folder)
        row = {"job_id": job, "task": TASK, "operation": operation, "state": "reserved", "reserved_at": utc_now(),
               "command": argv, "source_sha256": source, "module_before": native.digest(native.STAGE / native.MODULE),
               "frozen_inputs": {str(p.relative_to(ROOT)): native.digest(p) for p in inputs},
               "preservation_before": preservation, "human_approval": "pending", "visual_verified": False}
        atomic_json(path, row)
        startup, _ = native.helpers()
        env = startup.environment()
        env["NN_NATIVE_FRONTEND_OUTPUT"] = str(folder / "result.json")
        with (folder / "console.log").open("xb") as output:
            (folder / "console.log").chmod(0o600)
            child = subprocess.Popen(argv, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                     stdout=output, stderr=subprocess.STDOUT)
            row.update(state="running_unknown", pid=child.pid)
            atomic_json(path, row)
            print(json.dumps({"job_id": job, "state": "running_unknown"}), flush=True)
            code = child.wait()
        row.update(state="blocked", exit_code=code, process_exit_observed=True, finished_at=utc_now())
        atomic_json(path, row)
        row["summary"] = native.summarize(folder / ("console.log" if operation == "build" else "engine.log"))
        row["module_sha256"] = native.digest(native.STAGE / native.MODULE)
        if operation == "build" and code == 0:
            native.publish_loader_inventory(row)
        row["preservation_after"] = audit()
        if native.manifest(native.SOURCE) != source or any(native.digest(ROOT / p) != h for p, h in row["frozen_inputs"].items()):
            raise StudioError("Frozen source/runner/recipe/tests changed during execution")
        row["result"] = load_json(folder / "result.json") if (folder / "result.json").exists() else {}
        good = type(code) is int and code == 0
        if operation == "build":
            good &= not row["summary"]["build_failed_marker"]
        else:
            good &= row["summary"]["error_count"] == row["summary"]["fatal_count"] == 0 and row["summary"]["normal_shutdown"]
            good &= (row["result"].get("state") == "native_frontend_schema_verified" if operation == "schema" else verified_result(row["result"]))
        row["state"] = "completed" if good else "blocked"
        atomic_json(path, row)
        print(json.dumps({k: row[k] for k in ("job_id", "state", "exit_code", "summary", "result", "preservation_after")}, indent=2))
        return 0 if good else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build", "schema", "verify", "audit"))
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.operation == "audit":
        if args.execute:
            parser.error("audit is read-only")
        with resource_lock("integrator", ROOT), resource_lock("unreal-editor", ROOT):
            print(json.dumps(audit(), indent=2))
        return 0
    if not args.execute:
        print(json.dumps({"state": "preview", "command": command(args.operation, BUILD / "PREVIEW"), "graphical_window": False}, indent=2))
        return 0
    return run(args.operation)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (StudioError, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(json.dumps({"state": "blocked_preserve_and_review", "error": str(exc)}))
        raise SystemExit(1)
