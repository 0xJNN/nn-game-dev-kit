#!/usr/bin/env python3
"""Exact-source, local-only native lobby gates. Preview unless --execute is explicit.

No interactive launcher, retry, reconciliation, broad baseline exclusions or service control.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
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
from pipeline.common import StudioError, atomic_json, load_json, resource_lock, utc_now

TASK = "hero-native-team-loop-fix-2026-11-07"
SOURCE = Path(__file__).with_name("NovanodeTraining")
WORK = ROOT / ".studio/lyra/projects/LyraStarterGame"
STAGE = WORK / "Plugins/GameFeatures/NovanodeTraining"
ENGINE = Path("/run/media/d/SEARCHX_WORK/Unreal/engines/5.8.4")
EVIDENCE = ROOT / ".studio/evidence"
BUILD = ROOT / ".studio/builds/hero-native-lobby"
INSTALL = EVIDENCE / "hero-native-lobby-install.json"
PRESERVED = EVIDENCE / "hero-native-lobby-preservation-start-2026-11-07.json"
BASELINE = BUILD / "original-inventory.json"
LOBBY = "/NovanodeTraining/Maps/L_TrainingLobby"
RECIPE = Path(__file__).with_name("prepare_native_training.py")
GENERATED = {"Binaries", "Intermediate", "Saved", "DerivedDataCache", "__pycache__"}
MODULE = "Binaries/Linux/libUnrealEditor-NovanodeTraining.so"
LOADER = "Binaries/Linux/UnrealEditor.modules"


def digest(path):
    if path.is_symlink():
        raise StudioError("Symlink in a pinned training input")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def manifest(folder, *, generated=False):
    result = {}
    for directory, dirs, names in os.walk(folder, followlinks=False):
        if any((Path(directory) / d).is_symlink() for d in dirs):
            raise StudioError("Symlink directory in training manifest")
        dirs[:] = [d for d in dirs if generated or d not in GENERATED]
        for name in names:
            path = Path(directory) / name
            result[path.relative_to(folder).as_posix()] = digest(path)
    return result


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def repository_matches_checkpoint(revision, index, checkpoint):
    return revision == checkpoint["revision"] and index == checkpoint["index_sha256"]


def prior_guard():
    pinned = load_json(PRESERVED)
    for name, expected in pinned["identity"]["files_sha256"].items():
        # This one tracked documentation update is explicitly authorized; source/assets are not.
        if name == "docs/HERO_SANDBOX.md":
            continue
        if digest(ROOT / name) != expected:
            raise StudioError("Preserved source/content/binary/journal changed: " + name)
    for name, expected in pinned["prior_jobs_sha256"].items():
        if digest(ROOT / name) != expected:
            raise StudioError("Prior native job changed: " + name)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    index = hashlib.sha256(subprocess.check_output(["git", "ls-files", "--stage"], cwd=ROOT)).hexdigest()
    repository_checkpoint = load_json(EVIDENCE / "hero-native-team-loop-checkpoint-2026-11-07.json")
    for name, expected in repository_checkpoint["prior_native_journals_sha256"].items():
        if digest(ROOT / name) != expected:
            raise StudioError("Checkpointed failed/native journal changed: " + name)
    if not repository_matches_checkpoint(revision, index, repository_checkpoint):
        raise StudioError("Revision/index changed; preserve parallel work and checkpoint")


def helpers():
    import lyra_startup as startup
    return startup, startup.repair.bootstrap()


def original_inventory():
    """Pin the complete verified base BEFORE installing the new plugin."""
    import lyra_startup as startup
    if BASELINE.exists():
        return load_json(BASELINE)
    manager = load_module("native_lobby_legacy_readonly", Path(__file__).with_name("manage.py"))
    manager.baseline()
    helper = startup.repair.bootstrap()
    binaries = {str(p.relative_to(WORK)): digest(p) for p in WORK.rglob("libUnrealEditor-*.so")}
    data = {"source_sha256": helper.source_inventory(WORK), "binary_sha256": binaries,
            "vault_sha256": helper.source_inventory(startup.repair.VAULT)}
    atomic_json(BASELINE, data)
    return data


def verify_baseline():
    prior_guard()
    startup, helper = helpers()
    if helper.active_editors():
        raise StudioError("Existing editor owner; close normally before integration")
    base = original_inventory()
    expected = dict(base["source_sha256"])
    if INSTALL.exists():
        receipt = load_json(INSTALL)
        expected.update(receipt["inventory_sha256"])
        verify_install(receipt)
    if helper.source_inventory(WORK) != expected:
        raise StudioError("Exact Lyra/plugin source manifest differs; no broad exclusions permitted")
    if helper.source_inventory(startup.repair.VAULT) != base["vault_sha256"]:
        raise StudioError("Vault identity changed")
    if any(digest(WORK / name) != value for name, value in base["binary_sha256"].items()):
        raise StudioError("An existing native module changed; preserve and review")
    return {"original_sources": len(base["source_sha256"]), "previous_binaries": len(base["binary_sha256"]),
            "exact_plugin_manifests": True, "prior_journals_preserved": True}


def verify_install(receipt):
    authored = manifest(SOURCE)
    if authored != receipt["sha256"]:
        raise StudioError("Authored source changed; cannot reuse this installation/build")
    for name, expected in authored.items():
        if digest(STAGE / name) != expected:
            raise StudioError("Installed source differs; preserve unfamiliar changes")
    actual_source = manifest(STAGE)
    actual_source = {k: v for k, v in actual_source.items() if not k.startswith("Content/")}
    if actual_source != authored:
        raise StudioError("Unrecognized installed source/config additions")


def plugin_inventory(authored):
    """Only the ten exact authored source/descriptor entries; no prefix exclusion."""
    prefix = STAGE.relative_to(WORK).as_posix() + "/"
    return {prefix + name: value for name, value in authored.items()}


def verify_partial_adoption(authored, installed, checkpoint):
    if installed != checkpoint["partial_installed_sha256"] or installed != authored:
        raise StudioError("Partial installation differs from the stopped checkpoint; preserve it")


def compile_correction_updates(previous, authored):
    allowed = {"Source/NovanodeTraining/Private/TrainingMatchComponent.cpp",
               "Source/NovanodeTraining/Private/TrainingAssets.cpp"}
    changed = {name for name in previous.keys() | authored.keys() if previous.get(name) != authored.get(name)}
    if set(previous) != set(authored) or changed != allowed:
        raise StudioError("Correction is not exactly the two measured owned-file fixes")
    return changed


def sync_compile_correction(receipt):
    checkpoint = load_json(EVIDENCE / "hero-native-team-loop-checkpoint-2026-11-07.json")
    previous = checkpoint["installed_source_sha256"]
    authored = manifest(SOURCE)
    expected_installed = {**previous, **{"Content/" + k: v for k, v in checkpoint["content_sha256"].items()}}
    if receipt["sha256"] != previous or manifest(STAGE) != expected_installed:
        raise StudioError("Stopped installed source changed; preserve it before correction")
    changed = team_loop_source_updates(previous, authored)
    if digest(EVIDENCE / ("hero-native-lobby-job-" + checkpoint["verify_job"] + ".json")) != checkpoint["verify_journal_sha256"]:
        raise StudioError("Original failed native journal changed; preserve and review")
    archive = ROOT / checkpoint["source_archive"] / "install-before-correction.json"
    if archive.exists():
        raise StudioError("Compile correction receipt already archived; reconcile rather than resubmit")
    archive.parent.mkdir(parents=True, exist_ok=True)
    with archive.open("xb") as output:
        output.write(INSTALL.read_bytes())
    archive.chmod(0o444)
    for name in changed:
        shutil.copy2(SOURCE / name, STAGE / name)
    updated = {"sha256": authored, "inventory_sha256": plugin_inventory(authored),
               "installed_at": utc_now(), "previous_install_archive": str(archive.relative_to(ROOT)),
               "measured_compile_fix_paths": sorted(changed)}
    atomic_json(INSTALL, updated)
    return updated


def asset_types_correction_updates(previous, authored):
    allowed = {"Source/NovanodeTraining/Private/TrainingAssets.cpp"}
    changed = {name for name in previous.keys() | authored.keys() if previous.get(name) != authored.get(name)}
    if set(previous) != set(authored) or changed != allowed:
        raise StudioError("Correction is not exactly the measured AssetManagerTypes fix")
    return changed


def bootstrap_correction_updates(previous, authored):
    allowed = {"Source/NovanodeTraining/NovanodeTraining.Build.cs", "Source/NovanodeTraining/Private/TrainingAssets.cpp"}
    changed = {name for name in previous.keys() | authored.keys() if previous.get(name) != authored.get(name)}
    if set(previous) != set(authored) or changed != allowed:
        raise StudioError("Correction is not exactly the measured bootstrap mount/dependency fix")
    return changed


def gc_correction_updates(previous, authored):
    allowed = {"Source/NovanodeTraining/Private/TrainingAssets.cpp", "Source/NovanodeTraining/Private/TrainingReflectionAdapter.cpp"}
    changed = {name for name in previous.keys() | authored.keys() if previous.get(name) != authored.get(name)}
    if set(previous) != set(authored) or changed != allowed:
        raise StudioError("Correction is not exactly the measured scoped-GC lifetime fix")
    return changed


def mapid_source_updates(previous, authored):
    allowed = {"Source/NovanodeTraining/Private/TrainingAssets.cpp", "Source/NovanodeTraining/Public/TrainingReflectionAdapter.h"}
    changed = {name for name in previous.keys() | authored.keys() if previous.get(name) != authored.get(name)}
    if set(previous) != set(authored) or changed != allowed:
        raise StudioError("Correction is not exactly the observed native MapID recipe/migration fix")
    return changed


def initstate_source_updates(previous, authored):
    allowed = {"Source/NovanodeTraining/Private/TrainingMatchComponent.cpp"}
    changed = {name for name in previous.keys() | authored.keys() if previous.get(name) != authored.get(name)}
    if set(previous) != set(authored) or changed != allowed:
        raise StudioError("Correction is not exactly the observed Hero init-state binding fix")
    return changed


def probe_deferral_source_updates(previous, authored):
    allowed = {"Source/NovanodeTraining/Private/TrainingLobby.cpp"}
    changed = {name for name in previous.keys() | authored.keys() if previous.get(name) != authored.get(name)}
    if set(previous) != set(authored) or changed != allowed:
        raise StudioError("Correction is not exactly the measured opt-in probe deferral")
    return changed


def team_loop_source_updates(previous, authored):
    allowed = {"Source/NovanodeTraining/Private/TrainingMatchComponent.cpp",
               "Source/NovanodeTraining/Private/TrainingLobby.cpp",
               "Source/NovanodeTraining/Public/TrainingLobby.h",
               "Source/NovanodeTraining/Public/TrainingFlow.h"}
    changed = {name for name in previous.keys() | authored.keys() if previous.get(name) != authored.get(name)}
    if set(previous) != set(authored) or changed != allowed:
        raise StudioError("Correction is not exactly the diagnosed native team policy and loop evidence")
    return changed


def verified_loop_result(result):
    if not (result.get("passed") is True and result.get("ready_matches") == 2 and result.get("generation") == 2 and
            result.get("lobby_arrivals") == 3 and result.get("native_returns") == 2 and
            result.get("cleanups") == 2 and result.get("cleanup_valid") is True):
        return False
    matches = result.get("matches")
    if not isinstance(matches, list) or len(matches) != 2:
        return False
    for match in matches:
        if not isinstance(match, dict) or match.get("human_ready") is not True:
            return False
        if any(match.get(name) != 3 for name in ("total_bots", "owned_bots", "ready_bots", "rival_bots")):
            return False
        if match.get("match_components") != 1:
            return False
        human, rival = match.get("human_team"), match.get("rival_team")
        if (not isinstance(human, (int, float)) or isinstance(human, bool) or
                not isinstance(rival, (int, float)) or isinstance(rival, bool) or
                not 0 <= human < 255 or not 0 <= rival < 255 or human == rival):
            return False
    return True


def validate_mapid_migration(before, after):
    changed = {name for name in before.keys() | after.keys() if before.get(name) != after.get(name)}
    if not before or set(before) != set(after) or changed != {"Experiences/DA_HeroTraining.uasset"}:
        raise StudioError("MapID migration changed other assets or did not change exactly the definition")


def loader_inventory(engine_manifest, target_manifest, binary, successful_exit):
    engine_id = engine_manifest.get("BuildId")
    if type(successful_exit) is not int or successful_exit != 0 or not engine_id or engine_id != target_manifest.get("BuildId"):
        raise StudioError("A source-exact successful build and matching engine/target BuildIds are required")
    if binary.is_symlink() or not binary.is_file():
        raise StudioError("Actual owned compiled ELF is required")
    with binary.open("rb") as stream:
        if stream.read(4) != b"\x7fELF":
            raise StudioError("Actual owned compiled ELF is required")
    return {"BuildId": engine_id, "Modules": {"NovanodeTraining": "libUnrealEditor-NovanodeTraining.so"}}


def publish_loader_inventory(row):
    data = loader_inventory(load_json(ENGINE / "Engine/Binaries/Linux/UnrealEditor.modules"),
                            load_json(WORK / "Binaries/Linux/UnrealEditor.modules"), STAGE / MODULE, row["exit_code"])
    destination = STAGE / LOADER
    if destination.exists():
        if load_json(destination) != data or not proven_loader_reuse(journals(), digest(destination), row.get("module_before")):
            raise StudioError("Own loader inventory already exists without matching provenance; preserve rather than overwrite")
        row["loader_manifest_reused_without_write"] = True
    else:
        with destination.open("x") as output:
            output.write(json.dumps(data, indent=2) + "\n")
    row["loader_manifest_sha256"] = digest(destination)
    row["loader_manifest_origin"] = "owned_additive_loader_inventory_after_observed_UBT_success_not_a_build_receipt"
    row["loader_build_id"] = data["BuildId"]


def proven_loader_reuse(previous_builds, loader_hash, previous_module):
    return any(r.get("operation") == "build" and r.get("state") == "completed" and
               type(r.get("exit_code")) is int and r["exit_code"] == 0 and previous_module is not None and
               r.get("module_sha256") == previous_module and r.get("loader_manifest_sha256") == loader_hash
               for r in previous_builds)


def install():
    if INSTALL.exists():
        receipt = load_json(INSTALL)
        if manifest(SOURCE) != receipt["sha256"]:
            receipt = sync_compile_correction(receipt)
        verify_install(receipt)
        return receipt["sha256"]
    authored = manifest(SOURCE)
    adopted = False
    if STAGE.exists():
        checkpoint = load_json(EVIDENCE / "hero-native-lobby-preflight-checkpoint-2026-11-07.json")
        verify_partial_adoption(authored, manifest(STAGE, generated=True), checkpoint)
        adopted = True
    else:
        for name in authored:
            target = STAGE / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SOURCE / name, target)
    _, helper = helpers()
    inventory = plugin_inventory(authored)
    expected = dict(original_inventory()["source_sha256"])
    expected.update(inventory)
    if helper.source_inventory(WORK) != expected:
        raise StudioError("Project inventory differs from base plus exact owned plugin entries")
    row = {"sha256": authored, "inventory_sha256": inventory, "installed_at": utc_now(),
           "adopted_exact_stopped_preflight_copy": adopted}
    atomic_json(INSTALL, row)
    verify_install(row)
    return authored


def journals():
    return [load_json(p) for p in sorted(EVIDENCE.glob("hero-native-lobby-job-*.json"))]


def ensure_no_pending():
    for path in EVIDENCE.glob("hero-*-job-*.json"):
        row = load_json(path)
        if row.get("state") in {"reserved", "running_unknown", "outcome_unknown"}:
            raise StudioError("Unfinished native operation: reconcile instead of resubmitting")


def require_phase(operation, source, content):
    phases = {"schema": "build", "prepare": "schema", "repair-map-id": "schema", "validate-assets": "schema", "verify": "prepare"}
    previous = phases.get(operation)
    if not previous:
        return
    previous_operations = {previous, "repair-map-id", "validate-assets"} if operation == "verify" else {previous}
    candidates = [r for r in journals() if r.get("operation") in previous_operations and r.get("state") == "completed" and
                  type(r.get("exit_code")) is int and r["exit_code"] == 0 and r.get("source_sha256") == source and
                  r.get("module_sha256") == digest(STAGE / MODULE)]
    if len(candidates) != 1:
        raise StudioError("No unique source-exact successful prerequisite: " + previous)
    if candidates[0].get("loader_manifest_sha256") != digest(STAGE / LOADER):
        raise StudioError("Exact owned native loader inventory differs")
    if operation == "verify" and content != candidates[0].get("content_after"):
        raise StudioError("Owned assets differ from the exact prepared manifest")
    if operation == "repair-map-id":
        checkpoint = load_json(EVIDENCE / "hero-native-lobby-mapid-checkpoint-2026-11-07.json")
        if content != checkpoint["content_sha256"]:
            raise StudioError("Asset parent differs from the exact successful preparation")
        parent = EVIDENCE / ("hero-native-lobby-job-" + checkpoint["asset_parent_job_id"] + ".json")
        if digest(parent) != checkpoint["asset_parent_journal_sha256"]:
            raise StudioError("Successful asset parent journal changed; preserve and review")
    if operation == "validate-assets":
        checkpoint = load_json(EVIDENCE / "hero-native-team-loop-checkpoint-2026-11-07.json")
        if content != checkpoint["content_sha256"]:
            raise StudioError("Previously repaired asset manifest differs; no reprepare allowed")
        parent = EVIDENCE / ("hero-native-lobby-job-" + checkpoint["asset_parent_job_id"] + ".json")
        if digest(parent) != checkpoint["asset_parent_journal_sha256"]:
            raise StudioError("Repaired asset parent journal changed; preserve and review")


def summarize(path):
    text = path.read_text(errors="replace") if path.exists() else ""
    owned = []
    for line in text.splitlines():
        match = re.search(r"(?:/|^)(Training\w*\.(?:h|cpp))(?::(\d+):\d+|\((\d+)\)):\s*(?:fatal )?(error|warning):\s*(.*)", line)
        if match:
            owned.append({"file": match[1], "line": int(match[2] or match[3]), "severity": match[4], "message": match[5][:600]})
    return {"log_sha256": digest(path) if path.exists() else None,
            "fatal_count": len(re.findall(r"Fatal error:|Critical error:|Assertion failed:", text, re.I)),
            "error_count": len(re.findall(r"Log\w+:\s*Error:", text)),
            "normal_shutdown": bool(re.search(r"LogExit:\s*(?:Display:\s*)?Exiting\.", text)),
            "owned_diagnostics": owned[:32],
            "build_failed_marker": bool(re.search(r"Result:\s*Failed|BUILD FAILED|error :", text))}


def command(operation, folder):
    if operation == "build":
        return [str(ENGINE / "Engine/Build/BatchFiles/Linux/Build.sh"), "LyraEditor", "Linux", "Development",
                "-Project=" + str(WORK / "Lyra.uproject"), "-Module=NovanodeTraining", "-EnablePlugins=NovanodeTraining",
                "-WaitMutex", "-NoHotReload", "-MaxParallelActions=6"]
    import lyra_startup as startup
    common = [arg + ",[/Script/PythonScriptPlugin.PythonScriptPluginSettings]:bRemoteExecution=False"
              if arg.startswith("-ini:Engine:") else arg for arg in startup.common_arguments()]
    common = [arg + ",[/Script/EngineSettings.GameMapsSettings]:GameDefaultMap=" + LOBBY
              if arg.startswith("-ini:Engine:") else arg for arg in common]
    result = [str(ENGINE / "Engine/Binaries/Linux/UnrealEditor-Cmd"), str(WORK / "Lyra.uproject"),
              *common, "-EnablePlugins=NovanodeTraining,PythonScriptPlugin,EditorScriptingUtilities",
              "-unattended", "-NullRHI", "-nosound", "-AbsLog=" + str(folder / "engine.log")]
    if operation == "verify":
        result.insert(2, LOBBY)
        result += ["-game", "-DisablePython", "-NovanodeTrainingProbe=" + str(folder / "result.json"),
                   "-NovanodeTrainingDiagnostics=" + str(folder / "initialization.jsonl")]
    else:
        if operation in ("schema", "prepare", "repair-map-id"):
            result += ["-DPCVars=GameFeaturePlugin.SkipBuiltInGameFeatures=1"]
        result += ["-run=pythonscript", "-script=" + str(RECIPE)]
    return result


def run(operation):
    if os.environ.get("NOVANODE_TASK_ID") != TASK:
        raise StudioError("Native execution requires the reviewed bounded task contract")
    with resource_lock("integrator", ROOT), resource_lock("unreal-editor", ROOT):
        ensure_no_pending()
        if any(row.get("task") == TASK and row.get("operation") == operation for row in journals()):
            raise StudioError("Phase attempt already exists; no automatic retries")
        prior_guard()
        _, helper = helpers()
        if helper.active_editors():
            raise StudioError("Existing editor owner; close normally before integration")
        source = install() if operation == "build" else load_json(INSTALL)["sha256"]
        preservation = verify_baseline()
        verify_install(load_json(INSTALL))
        content = manifest(STAGE / "Content", generated=True)
        if operation == "prepare" and content:
            raise StudioError("Owned Content already exists; never overwrite a partial preparation")
        require_phase(operation, source, content)
        if operation in ("build", "schema", "validate-assets", "verify"):
            gpu = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=10, check=True)
            if int(gpu.stdout.splitlines()[0]) < 2048:
                raise StudioError("Insufficient confirmed VRAM; do not stop user services")
        job = operation + "-" + uuid.uuid4().hex[:12]
        folder = BUILD / job
        folder.mkdir(parents=True, exist_ok=False)
        path = EVIDENCE / ("hero-native-lobby-job-" + job + ".json")
        argv = command(operation, folder)
        row = {"job_id": job, "task": TASK, "operation": operation, "state": "reserved", "reserved_at": utc_now(),
               "source_sha256": source, "recipe_sha256": digest(RECIPE), "runner_sha256": digest(Path(__file__)),
               "command": argv, "content_before": content, "preservation_before": preservation,
               "module_before": digest(STAGE / MODULE) if (STAGE / MODULE).is_file() else None,
               "asset_parent_job_id": ("prepare-09db4c3c7434" if operation == "repair-map-id" else
                                       "repair-map-id-860afbec0776" if operation == "validate-assets" else None),
               "frozen_inputs": {str(p.relative_to(ROOT)): digest(p) for p in (
                   Path(__file__), RECIPE, ROOT / "tests/test_native_training.py",
                   ROOT / f".studio/tasks/{TASK}.json")},
               "human_approval": "pending", "visual_verified": False}
        atomic_json(path, row)
        import lyra_startup as startup
        env = startup.environment()
        env.update(NN_TRAINING_OPERATION=operation, NN_TRAINING_OUTPUT=str(folder / "result.json"))
        console = folder / "console.log"
        with console.open("xb") as output:
            child = subprocess.Popen(argv, cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT)
            try:
                ticks = Path(f"/proc/{child.pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
            except FileNotFoundError:
                ticks = None
            row.update(state="running_unknown", pid=child.pid, process_start_ticks=ticks)
            atomic_json(path, row)
            print(json.dumps({"job_id": job, "operation": operation, "state": "running_unknown"}), flush=True)
            code = child.wait()
        # A real exit is durable before any fallible verification. No fabricated success.
        row.update(exit_code=code, process_exit_observed=True, finished_at=utc_now(), state="blocked")
        atomic_json(path, row)
        try:
            row["summary"] = summarize(console if operation == "build" else folder / "engine.log")
            if any(digest(ROOT / name) != value for name, value in row["frozen_inputs"].items()):
                raise StudioError("Frozen task/runner/recipe/fixture changed during execution; stop")
            row["preservation_after"] = verify_baseline()
            row["content_after"] = manifest(STAGE / "Content", generated=True)
            row["module_sha256"] = digest(STAGE / MODULE) if (STAGE / MODULE).is_file() else None
            if operation == "build" and code == 0 and row["module_sha256"]:
                publish_loader_inventory(row)
            elif (STAGE / LOADER).is_file():
                row["loader_manifest_sha256"] = digest(STAGE / LOADER)
            result = folder / "result.json"
            row["result"] = load_json(result) if result.exists() else {}
            good = type(code) is int and code == 0 and bool(row["module_sha256"])
            if operation == "build":
                good = good and not row["summary"]["build_failed_marker"]
            else:
                good = good and row["summary"]["fatal_count"] == row["summary"]["error_count"] == 0 and row["summary"]["normal_shutdown"]
                expected = {"schema": "schema_verified", "prepare": "prepared", "repair-map-id": "assets_repaired", "validate-assets": "assets_loaded"}.get(operation)
                good = good and (row["result"].get("state") == expected if expected else verified_loop_result(row["result"]))
            if operation == "repair-map-id":
                validate_mapid_migration(content, row["content_after"])
            elif operation != "prepare" and row["content_after"] != content:
                good = False
            row["state"] = "completed" if good else "blocked"
        except (Exception, KeyboardInterrupt):
            row["post_exit_verification"] = "failed_or_interrupted"
            atomic_json(path, row)
            raise
        atomic_json(path, row)
        print(json.dumps({k: row[k] for k in ("job_id", "state", "exit_code", "summary", "result", "preservation_after")}, indent=2))
        return 0 if row["state"] == "completed" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build", "schema", "prepare", "repair-map-id", "validate-assets", "verify", "audit"))
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.operation == "audit":
        if args.execute:
            parser.error("audit is read-only")
        with resource_lock("integrator", ROOT), resource_lock("unreal-editor", ROOT):
            print(json.dumps(verify_baseline(), indent=2))
        return 0
    if not args.execute:
        print(json.dumps({"state": "preview", "operation": args.operation,
                          "command": command(args.operation, BUILD / "PREVIEW"),
                          "interactive_window": False, "notice": "Requires the reviewed task, exact prerequisites and no pending operation."}, indent=2))
        return 0
    return run(args.operation)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (StudioError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"state": "blocked_preserve_and_review", "error": str(exc)}))
        raise SystemExit(1)
