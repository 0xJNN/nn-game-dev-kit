#!/usr/bin/env python3
"""Machine-local Lyra integration, without reading sample source into AI context.

Each engine command has a durable identity and local-only raw logs. Never reuses
an attempt's filenames; an unfinished job must be reconciled, not resubmitted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / ".studio/scripts"))
from pipeline.common import StudioError, atomic_json, resource_lock, utc_now

SOURCE = Path(__file__).resolve().parent / "NovanodeHeroes"
STAGE = ROOT / ".studio/lyra/projects/LyraStarterGame/Plugins/NovanodeHeroes"
WORK = STAGE.parents[1]
ENGINE = Path("/run/media/d/SEARCHX_WORK/Unreal/engines/5.8.4")
EVIDENCE = ROOT / ".studio/evidence"
BUILDS = ROOT / ".studio/builds/hero-sandbox"
PREFIX = "Plugins/NovanodeHeroes/"
MAP_V1 = "/NovanodeHeroes/Maps/L_HeroSandbox_v1"
MAP_V2 = "/NovanodeHeroes/Maps/L_HeroSandbox_v2"
TEXT_MAP = "/NovanodeHeroes/Maps/L_TextCalibration_v2"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def baseline():
    import lyra_startup as startup
    repair = startup.repair
    fixed = json.loads(repair.STATE.read_text())
    helper = repair.bootstrap()
    if helper.active_editors():
        raise StudioError("Existing editor owner: close normally before integration")
    if fixed.get("state") != "native_build_machine_verified" or not startup.startup_verified():
        raise StudioError("Verified baseline startup/build is required")
    inventory = helper.source_inventory(repair.WORK)
    existing = {key: value for key, value in inventory.items() if not key.startswith(PREFIX)}
    if existing != fixed["expected_source_hashes"]:
        raise StudioError("Existing Lyra source/config/descriptor changed: stop and review")
    original = json.loads(helper.MANIFEST.read_text())["sha256"]
    if helper.source_inventory(repair.VAULT) != original:
        raise StudioError("Original vault baseline changed: stop and review")
    return {"baseline_file_count": len(existing), "existing_lyra_hashes_preserved": True,
            "vault_hashes_preserved": True}


def sync():
    """Only overwrite our previous staged bytes, never unfamiliar local work."""
    receipt_path = EVIDENCE / "hero-sandbox-install.json"
    previous = json.loads(receipt_path.read_text()) if receipt_path.exists() else {"sha256": {}}
    verify_staged_code_paths(previous["sha256"])
    authored = {p.relative_to(SOURCE).as_posix(): digest(p) for p in SOURCE.rglob("*") if p.is_file()}
    for name, expected in previous["sha256"].items():
        target = STAGE / name
        if not target.is_file() or digest(target) != expected:
            raise StudioError("Staged plugin has unrecognized changes; preserve and review")
    for name in authored:
        target = STAGE / name
        if target.exists() and name not in previous["sha256"]:
            raise StudioError("Destination exists without owned provenance; preserve it")
    if set(previous["sha256"]) - set(authored):
        raise StudioError("Removing staged source needs an explicit migration")
    for name in authored:
        source, target = SOURCE / name, STAGE / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or digest(target) != authored[name]:
            shutil.copy2(source, target)
    atomic_json(receipt_path, {"schema_version": 1, "updated_at": utc_now(), "sha256": authored,
                              "source": str(SOURCE.relative_to(ROOT)), "stage": str(STAGE.relative_to(ROOT))})
    return authored


def verify_staged_code_paths(hashes):
    expected = {name for name in hashes if name.startswith("Source/")}
    current = {path.relative_to(STAGE).as_posix() for path in (STAGE / "Source").rglob("*") if path.is_file()}
    if current != expected:
        raise StudioError("Unrecognized staged source additions/removals; preserve and review before compiling")


def identity(process):
    return {"pid": process.pid,
            "process_start_ticks": Path(f"/proc/{process.pid}/stat").read_text().rsplit(")", 1)[1].split()[19]}


def verify_build_identity(hashes, module, journals):
    if not module.is_file() or module.read_bytes()[:4] != b"\x7fELF":
        raise StudioError("Native plugin ELF module missing")
    binary_hash = digest(module)
    for row in journals:
        if (row.get("operation") == "build" and row.get("state") == "completed" and
                type(row.get("exit_code")) is int and row["exit_code"] == 0 and
                row.get("source_sha256") == hashes and row.get("native_module_sha256") == binary_hash):
            return row["job_id"]
    raise StudioError("No successful native build matches these exact source and binary hashes")


def verify_prepared_assets(journals, required_map="Maps/L_HeroSandbox_v1.umap"):
    content = STAGE / "Content"
    current = {p.relative_to(content).as_posix(): digest(p) for p in content.rglob("*") if p.is_file()}
    for row in journals:
        data = row.get("preparation", {})
        if (row.get("operation") in ("prepare", "prepare-v2", "validate-v2") and row.get("state") == "completed" and
                data.get("state") == "prepared" and data.get("generated_sha256") == current and
                required_map in current):
            return row["job_id"]
    raise StudioError("Own map/imported assets changed or no complete preparation exists; preserve and review")


def summarize(log):
    # Restricted sample logs stay on disk. Return only categories and diagnostics
    # originating in this task's OWN authored files, not arbitrary build excerpts.
    text = log.read_text(errors="replace") if log.exists() else ""
    own = [line for line in text.splitlines() if re.search(
        r"(?:HeroSandbox|HeroCombatRules|HeroPresentation)\.(?:cpp|h)(?:\(\d|:\d).*?(?:error|warning):", line)]
    return {"log_sha256": digest(log) if log.exists() else None,
            "fatal_count": len(re.findall(r"Fatal error:|Critical error:|Assertion failed:", text, re.I)),
            "error_severity_count": len(re.findall(r"Log\w+:\s*Error:", text)),
            "normal_exit_marker": bool(re.search(r"LogExit:\s*(?:Display:\s*)?Exiting\.", text)),
            "owned_diagnostics": own[:24]}


def run(operation, *, job_id=None, timeout=20, dry_run=False):
    if operation == "stop":
        from pipeline.hero_stop import stop_session
        result = stop_session(ROOT, ENGINE / "Engine/Binaries/Linux/UnrealEditor", WORK / "Lyra.uproject",
                              MAP_V2, job_id=job_id, timeout=timeout, dry_run=dry_run)
        print(json.dumps(result, indent=2))
        return 0 if result["state"] in ("stopped", "not_running", "dry_run") else 1
    if operation == "text-capture":
        raise StudioError("Original-text capture fixture is checkpointed after a crash and disabled pending review; no engine started")
    import lyra_startup as startup
    with resource_lock("integrator", ROOT), resource_lock("unreal-editor", ROOT):
        preserved = baseline()
        uses_v2 = operation in ("smoke-v2", "probe-v2", "probe-v2-rendered", "editor-v2", "play-v2")
        journals = [json.loads(path.read_text()) for path in EVIDENCE.glob("hero-sandbox-job-*.json")]
        reconcile_journal = None
        # Refuse an un-reconciled command, even when its PID no longer exists.
        for path in EVIDENCE.glob("hero-sandbox-job-*.json"):
            if json.loads(path.read_text()).get("state") in ("reserved", "running_unknown"):
                raise StudioError("Unfinished owned job: reconcile " + str(path.relative_to(ROOT)))
        if operation == "build":
            hashes = sync()
        else:
            receipt = json.loads((EVIDENCE / "hero-sandbox-install.json").read_text())
            hashes = receipt["sha256"]
            verify_staged_code_paths(hashes)
            authored_paths = {path.relative_to(SOURCE).as_posix() for path in SOURCE.rglob("*") if path.is_file()}
            if authored_paths != set(hashes):
                raise StudioError("Authored source file set changed; build before using cached binaries")
            if any(digest(STAGE / name) != value or digest(SOURCE / name) != value for name, value in hashes.items()):
                raise StudioError("Source/stage/build identity differs; build first")
            verify_build_identity(hashes, STAGE / "Binaries/Linux/libUnrealEditor-NovanodeHeroes.so", journals)
            if operation == "validate-v2":
                content = STAGE / "Content"
                current = {path.relative_to(content).as_posix(): digest(path) for path in content.rglob("*") if path.is_file()}
                candidates = [row for row in journals if row.get("operation") == "prepare-v2" and
                              row.get("preparation", {}).get("state") == "prepared" and
                              row["preparation"].get("generated_sha256") == current and
                              row.get("exit_code") == 0 and row.get("summary", {}).get("normal_exit_marker") is True and
                              row.get("summary", {}).get("fatal_count") == 0]
                if len(candidates) != 1:
                    raise StudioError("Read-only reconciliation needs one exact completed preparation artifact identity")
                reconcile_journal = EVIDENCE / ("hero-sandbox-job-" + candidates[0]["job_id"] + ".json")
            if operation in ("smoke", "editor", "probe", "smoke-v2", "editor-v2", "play-v2", "probe-v2", "probe-v2-rendered", "text-capture"):
                required_map = "Maps/L_TextCalibration_v2.umap" if operation == "text-capture" else (
                    "Maps/L_HeroSandbox_v2.umap" if uses_v2 else "Maps/L_HeroSandbox_v1.umap")
                verify_prepared_assets(journals, required_map)
        job_id = operation + "-" + uuid.uuid4().hex[:12]
        folder = BUILDS / job_id
        folder.mkdir(parents=True)
        journal = EVIDENCE / ("hero-sandbox-job-" + job_id + ".json")
        log = folder / "engine.log"
        console = folder / "console.log"
        common = startup.common_arguments()
        common = [a + ",[/Script/PythonScriptPlugin.PythonScriptPluginSettings]:bRemoteExecution=False"
                  if a.startswith("-ini:Engine:") else a for a in common]
        if operation == "build":
            argv = [str(ENGINE / "Engine/Build/BatchFiles/Linux/Build.sh"), "LyraEditor", "Linux", "Development",
                    "-Project=" + str(WORK / "Lyra.uproject"), "-WaitMutex", "-NoHotReload", "-MaxParallelActions=6"]
        else:
            argv = [str(ENGINE / "Engine/Binaries/Linux/UnrealEditor-Cmd"), str(WORK / "Lyra.uproject"),
                    *common, "-unattended", "-NullRHI", "-nosound", "-AbsLog=" + str(log)]
            if operation in ("prepare", "prepare-v2", "validate-v2"):
                recipe = "validate_presentation.py" if operation == "validate-v2" else (
                    "prepare_presentation.py" if operation == "prepare-v2" else "prepare_unreal.py")
                argv += ["-EnablePlugins=PythonScriptPlugin,EditorScriptingUtilities"]
                if operation == "validate-v2":
                    # Documented headless asset-commandlet lifecycle: do not initialize
                    # unrelated full-editor UI helpers for a read-only package check.
                    # Still require this fresh run to have zero errors and normal exit.
                    argv += ["-run=pythonscript", "-script=" + str(Path(__file__).with_name(recipe))]
                else:
                    argv += ["-ExecutePythonScript=" + str(Path(__file__).with_name(recipe))]
            elif operation == "test":
                argv += ["-ExecCmds=Automation RunTests Novanode.Heroes;Quit", "-TestExit=Automation Test Queue Empty",
                         "-ReportExportPath=" + str(folder / "automation")]
            elif operation in ("smoke", "smoke-v2"):
                argv.insert(2, MAP_V2 if uses_v2 else MAP_V1)
                argv += ["-game", "-DisablePython",
                         "-HeroSandboxSmoke=" + str(folder / "smoke.json")]
            elif operation in ("probe", "probe-v2", "probe-v2-rendered"):
                argv.insert(2, MAP_V2 if uses_v2 else MAP_V1)
                argv += ["-game", "-DisablePython", "-ExecCmds=t.MaxFPS 60",
                         "-HeroPresentationProbe=" + str(folder / "presentation.json")]
                if operation == "probe-v2-rendered":
                    gpu = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                                         capture_output=True, text=True, timeout=10)
                    if gpu.returncode or int(gpu.stdout.splitlines()[0]) < 8192:
                        raise StudioError("Insufficient confirmed probe VRAM; do not stop user services")
                    argv.remove("-NullRHI")
                    argv += ["-RenderOffscreen", "-ForceRes", "-ResX=1280", "-ResY=720", "-HeroRenderedProbe"]
            elif operation == "text-capture":
                gpu = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                                     capture_output=True, text=True, timeout=10)
                if gpu.returncode or int(gpu.stdout.splitlines()[0]) < 8192:
                    raise StudioError("Insufficient confirmed capture VRAM; do not stop user services")
                argv.remove("-NullRHI")
                argv.insert(2, TEXT_MAP)
                # Original-text fixture, not a Lyra gameplay readiness test.
                # Keep its base GameMode with matching base instance/player/viewport
                # so the sample's front-end/loading flow cannot cover the test.
                index = next(i for i, value in enumerate(argv) if value.startswith("-ini:Engine:"))
                argv[index] += "," + ",".join((
                    "[/Script/EngineSettings.GameMapsSettings]:GameInstanceClass=/Script/Engine.GameInstance",
                    "[/Script/Engine.Engine]:LocalPlayerClassName=/Script/Engine.LocalPlayer",
                    "[/Script/Engine.Engine]:GameViewportClientClassName=/Script/Engine.GameViewportClient",
                ))
                argv += ["-game", "-DisablePython", "-RenderOffscreen", "-ForceRes", "-ResX=1280", "-ResY=720",
                         "-ExecCmds=t.MaxFPS 60", "-HeroTextCapture=" + str(folder / "text.png")]
            else:
                if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
                    raise StudioError("No graphical session")
                gpu = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                                     capture_output=True, text=True, timeout=10)
                if gpu.returncode or int(gpu.stdout.splitlines()[0]) < 8192:
                    raise StudioError("Insufficient confirmed VRAM; do not stop user services")
                argv[0] = str(ENGINE / "Engine/Binaries/Linux/UnrealEditor")
                argv = [a for a in argv if a not in ("-unattended", "-NullRHI", "-nosound")]
                if operation in ("editor", "editor-v2", "play-v2"): argv.insert(2, MAP_V2 if uses_v2 else MAP_V1)
                if operation == "play-v2":
                    argv += ["-game", "-DisablePython", "-windowed", "-ResX=1280", "-ResY=720"]
        state = {"state": "reserved", "job_id": job_id, "operation": operation, "started_at": utc_now(),
                 "command": argv, "source_sha256": hashes, "preservation": preserved,
                 "raw_logs_local_only": [str(console.relative_to(ROOT)), str(log.relative_to(ROOT))],
                 "human_approval": "pending"}
        atomic_json(journal, state)
        env = startup.environment()
        env["NN_HERO_BUILD_DIR"] = str(folder)
        if reconcile_journal is not None:
            env["NN_HERO_RECONCILE_JOURNAL"] = str(reconcile_journal)
        with console.open("xb") as output:
            process = subprocess.Popen(argv, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                       stdout=output, stderr=subprocess.STDOUT)
            state.update(state="running_unknown", **identity(process))
            atomic_json(journal, state)
            print(json.dumps({"job": str(journal.relative_to(ROOT)), "pid": process.pid, "operation": operation}), flush=True)
            code = process.wait()
        record_exit(state, journal, code, console if operation == "build" else log)
        if operation == "build" and code == 0:
            module = STAGE / "Binaries/Linux/libUnrealEditor-NovanodeHeroes.so"
            state["native_module_sha256"] = digest(module)
        if operation == "test":
            report_path = folder / "automation/index.json"
            report = json.loads(report_path.read_text(encoding="utf-8-sig")) if report_path.exists() else {}
            tests = [{"name": t.get("fullTestPath"), "state": t.get("state")} for t in report.get("tests", [])]
            state["automation"] = tests
            expected = {"Novanode.Heroes.Rules.Cooldown", "Novanode.Heroes.Rules.ComboAndDeduplication", "Novanode.Heroes.Rules.DashAndInvalidTime"}
            if len(tests) != 3 or {t["name"] for t in tests} != expected or any(t["state"] != "Success" for t in tests):
                state["state"] = "blocked"
        if operation in ("prepare", "prepare-v2", "validate-v2"):
            path = folder / "prepare.json"
            state["preparation"] = json.loads(path.read_text()) if path.exists() else {"state": "missing"}
            if state["preparation"].get("state") != "prepared": state["state"] = "blocked"
        if operation in ("smoke", "smoke-v2"):
            path = folder / "smoke.json"
            state["smoke"] = json.loads(path.read_text()) if path.exists() else {"state": "missing"}
            if state["smoke"].get("passed") is not True: state["state"] = "blocked"
        if operation in ("probe", "probe-v2", "probe-v2-rendered"):
            path = folder / "presentation.json"
            state["presentation"] = json.loads(path.read_text()) if path.exists() else {"state": "missing"}
            if state["presentation"].get("state") != "presentation_structure_observed_not_visual_approval":
                state["state"] = "blocked"
            if uses_v2 and (state["presentation"].get("usable_character_body_present") is not True or
                    state["presentation"].get("pawn_possessed") is not True or
                    state["presentation"].get("camera_view_target_is_pawn") is not True or
                    state["presentation"].get("camera_to_pawn_distance_cm", 0) < 150):
                state["state"] = "blocked"
            if operation == "probe-v2-rendered" and (state["presentation"].get("rendered_probe_requested") is not True or
                    state["presentation"].get("recently_rendered_character_body_components", 0) < 1):
                state["state"] = "blocked"
        if operation == "text-capture":
            path = folder / "text.png.json"
            state["capture"] = json.loads(path.read_text()) if path.exists() else {"state": "missing"}
            if state["capture"].get("state") != "original_text_calibration_captured" or state["capture"].get("foreign_visuals_excluded") is not True:
                state["state"] = "blocked"
        if operation in ("prepare", "prepare-v2", "validate-v2", "test", "smoke", "smoke-v2", "probe", "probe-v2", "probe-v2-rendered", "text-capture") and (state["summary"]["fatal_count"] or
                state["summary"]["error_severity_count"] or not state["summary"]["normal_exit_marker"]):
            state["state"] = "blocked"
        atomic_json(journal, state)
        safe = {k: v for k, v in state.items() if k not in ("command", "source_sha256", "raw_logs_local_only", "preparation")}
        if "preparation" in state:
            safe["preparation"] = {k: v for k, v in state["preparation"].items() if k != "generated_sha256"}
        print(json.dumps(safe, indent=2))
        return 0 if state["state"] == "completed" else 1


def record_exit(state, journal, code, log):
    """Persist the real child exit before a post-check can fail or be interrupted."""
    state.update(exit_code=code, finished_at=utc_now(), process_exit_observed=True)
    atomic_json(journal, state)
    try:
        preservation = baseline()
        summary = summarize(log)
    except (Exception, KeyboardInterrupt):
        state.update(state="blocked", post_exit_verification="failed_or_interrupted")
        atomic_json(journal, state)
        raise
    state.update(state="completed" if code == 0 else "blocked", preservation=preservation, summary=summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build", "prepare", "prepare-v2", "validate-v2", "test", "smoke", "smoke-v2", "probe", "probe-v2", "probe-v2-rendered", "text-capture", "editor", "editor-v2", "play-v2", "gold", "stop"))
    parser.add_argument("--job-id", help="stop only: exact play-v2 job when selection is ambiguous")
    parser.add_argument("--timeout", type=int, help="stop only: wait 1..60 seconds (default 20); never escalates")
    parser.add_argument("--dry-run", action="store_true", help="stop only: validate identity without sending a signal")
    args = parser.parse_args()
    if args.operation != "stop" and (args.job_id is not None or args.timeout is not None or args.dry_run):
        parser.error("--job-id, --timeout and --dry-run are stop-only options")
    try:
        raise SystemExit(run(args.operation, job_id=args.job_id, timeout=20 if args.timeout is None else args.timeout,
                             dry_run=args.dry_run))
    except KeyboardInterrupt:
        print(json.dumps({"state": "outcome_unknown", "reconciliation_required": True,
                          "error": "Interrupted: inspect the native journal and stop receipt; no blind retry"}))
        raise SystemExit(130)
    except (StudioError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"state": "stopped_preserve_and_review", "error": str(exc)}))
        raise SystemExit(1)
