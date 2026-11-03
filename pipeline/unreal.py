from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

from .common import ROOT, StudioError, config, load_json, project_path, resource_lock
from .process import run_process


def validate_source(root: Path = ROOT) -> dict:
    settings = config(root)
    project = project_path(settings["studio"]["project"], root)
    descriptor = load_json(project)
    if descriptor.get("EngineAssociation") != settings["unreal"]["version"]:
        raise StudioError("Unreal project association does not match studio.toml")
    if descriptor.get("Modules") != [{"Name": "NovanodeLab", "Type": "Runtime", "LoadingPhase": "Default"}]:
        raise StudioError("Unexpected Unreal runtime module declaration")
    required = ["Config/DefaultEngine.ini", "Config/DefaultInput.ini", "Config/DefaultGame.ini",
                "Source/NovanodeLab.Target.cs", "Source/NovanodeLabEditor.Target.cs",
                "Source/NovanodeLab/NovanodeLab.Build.cs",
                "Source/NovanodeLab/Private/StudioGameMode.cpp",
                "Source/NovanodeLab/Public/LabState.h"]
    for name in required:
        if not (project.parent / name).is_file():
            raise StudioError(f"Missing Unreal source/config: {name}")
    return {"status": "source_validated", "project": str(project),
            "native_build_verified": False, "human_approval": "pending"}


def engine_root(root: Path = ROOT) -> Path:
    value = os.environ.get("UE_ROOT")
    if not value:
        raise StudioError("Unreal is not configured. Install the licensed Linux editor yourself, "
                          "then set UE_ROOT to the folder containing Engine/. See docs/UNREAL.md")
    path = Path(value).expanduser().resolve()
    version = load_json(path / "Engine/Build/Build.version")
    actual = f"{version.get('MajorVersion')}.{version.get('MinorVersion')}"
    expected = config(root)["unreal"]["version"]
    if actual != expected:
        raise StudioError(f"Expected Unreal {expected}; UE_ROOT contains {actual}. Review the version before migrating.")
    for name in ("Engine/Binaries/Linux/UnrealEditor", "Engine/Build/BatchFiles/Linux/Build.sh",
                 "Engine/Build/BatchFiles/RunUAT.sh"):
        binary = path / name
        if not binary.is_file() or not os.access(binary, os.X_OK):
            raise StudioError(f"Missing executable in Unreal installation: {binary}")
    return path


def doctor(root: Path = ROOT) -> dict:
    result = {"project": validate_source(root), "target": "linux", "ready": False,
              "engine_version_family": config(root)["unreal"]["version"],
              "macos": "deferred", "native_validation": "not_assessed_by_doctor"}
    try:
        result.update(ready=True, engine_root=str(engine_root(root)))
    except StudioError as exc:
        result["setup_required"] = str(exc)
    return result


def commands(action: str, ue: Path, root: Path = ROOT) -> list[list[str]]:
    project = project_path(config(root)["studio"]["project"], root)
    editor = str(ue / "Engine/Binaries/Linux/UnrealEditor")
    headless = [editor, str(project), "-unattended", "-nop4", "-nosplash", "-nosound",
                "-stdout", "-FullStdOutLogOutput", "-NullRHI"]
    report = root / ".studio/evidence/unreal-automation"
    if action == "build":
        return [[str(ue / "Engine/Build/BatchFiles/Linux/Build.sh"), "NovanodeLabEditor", "Linux",
                 "Development", str(project), "-WaitMutex", "-NoHotReloadFromIDE"]]
    if action == "prepare":
        return [headless + ["-run=pythonscript", f"-script={root / 'scripts/unreal/prepare_project.py'}"]]
    if action == "test":
        return [headless + ["-ExecCmds=Automation RunTest Novanode.State.;Quit",
                            f"-ReportExportPath={report}"]]
    if action == "run":
        return [[editor, str(project), "/Game/Generated/Maps/NovanodeLab", "-game", "-vulkan", "-log"]]
    if action == "editor":
        return [[editor, str(project), "-vulkan", "-log"]]
    if action == "package":
        return [[str(ue / "Engine/Build/BatchFiles/RunUAT.sh"), "BuildCookRun", f"-project={project}",
                 "-platform=Linux", "-clientconfig=Development", "-noP4", "-utf8output", "-build",
                 "-cook", "-stage", "-pak", "-archive", f"-archivedirectory={root / '.studio/builds/unreal'}"]]
    if action == "smoke":
        return [[str(root / ".studio/builds/unreal/Linux/NovanodeLab.sh"), "-NullRHI", "-unattended",
                 "-nosound", f"-NovanodeSmokeReport={root / '.studio/evidence/unreal-startup.json'}"]]
    raise StudioError(f"Unknown Unreal action: {action}")


def verify_automation(path: Path) -> dict:
    report = load_json(path)
    tests = report.get("tests")
    if (not isinstance(tests, list) or len(tests) < 3 or report.get("failed") != 0
            or report.get("notRun") != 0 or report.get("inProcess", 0) != 0
            or any(test.get("state") != "Success" or test.get("errors", 0) for test in tests)
            or len({test.get("fullTestPath") for test in tests}) != len(tests)):
        raise StudioError("Unreal automation evidence is incomplete, skipped, duplicated, or failed")
    expected = {"Novanode.State.Prerequisites", "Novanode.State.Period", "Novanode.State.InvalidInputs"}
    if not expected.issubset({test.get("fullTestPath") for test in tests}):
        raise StudioError("Required Unreal state tests are missing")
    return {"status": "machine_verified", "scope": "native Unreal state tests only",
            "tests": len(tests), "human_approval": "pending", "evidence": str(path)}


def verify_smoke(path: Path) -> dict:
    report = load_json(path)
    checks = report.get("checks")
    expected = {"authored material loaded", "reference rejects missing prerequisites",
                "closed door blocks world-space ray", "open door clears collision ray",
                "reference completes with correct period"}
    if (report.get("status") != "passed" or report.get("human_approval") != "pending"
            or not isinstance(checks, list) or len(checks) != len(expected)
            or any(not isinstance(check, dict) or check.get("passed") is not True for check in checks)
            or {check.get("name") for check in checks} != expected):
        raise StudioError("Packaged Unreal runtime evidence is missing, contradictory, duplicated, or failed")
    return {"status": "machine_verified", "scope": "runtime outcomes, not physical keyboard or visual acceptance",
            "evidence": str(path), "human_approval": "pending"}


def run(action: str, execute=False, root: Path = ROOT) -> dict | int:
    validate_source(root)
    if not execute:
        guessed = Path(os.environ.get("UE_ROOT", "/path/to/UE_5.8"))
        return {"status": "dry_run", "commands": commands(action, guessed, root),
                "notice": "Requires an installed licensed Linux editor. Use --execute after reviewing setup."}
    if platform.system() != "Linux":
        raise StudioError("This Unreal pipeline currently targets Linux only")
    ue = engine_root(root)
    evidence = root / ".studio/evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    project = project_path(config(root)["studio"]["project"], root)
    if action not in {"build", "prepare"} and not (
        project.parent / "Content/Generated/Maps/NovanodeLab.umap"
    ).is_file():
        raise StudioError("Generated map missing. Build the editor module, then run `unreal prepare --execute`.")
    with resource_lock("unreal-editor", root):
        if action in {"run", "editor"}:
            return subprocess.call(commands(action, ue, root)[0], cwd=root)
        stale = {
            "prepare": evidence / "unreal-prepare.json",
            "test": evidence / "unreal-automation/index.json",
            "smoke": evidence / "unreal-startup.json",
        }.get(action)
        if stale:
            stale.parent.mkdir(parents=True, exist_ok=True)
            stale.unlink(missing_ok=True)
        timeout = config(root)["unreal"]["build_timeout_seconds"] if action in {"build", "package"} else config(root)["unreal"]["test_timeout_seconds"]
        for index, argv in enumerate(commands(action, ue, root)):
            result = run_process(argv, root, timeout, evidence / f"unreal-{action}-{index}.log")
            if result["reason"] != "completed":
                log_notice = f"see {result['log']}" if result.get("log") else "no command log was produced"
                raise StudioError(f"Unreal {action} outcome unknown ({result['reason']}); {log_notice}. "
                                  "Inspect logs and owned process/build state; reconcile before retrying.")
            if result["exit_code"] != 0:
                raise StudioError(f"Unreal {action} failed; see {result['log']}")
        if action == "test":
            return verify_automation(stale)
        if action == "prepare":
            report = load_json(stale)
            if report.get("status") != "assets_prepared":
                raise StudioError("Unreal asset preparation produced no valid evidence")
            return report
        if action == "smoke":
            return verify_smoke(stale)
        if action == "package" and not (root / ".studio/builds/unreal/Linux/NovanodeLab.sh").is_file():
            raise StudioError("Packaging exited successfully but the expected Linux launcher is missing")
        return {"status": "built" if action == "build" else "packaged_not_runtime_verified",
                "human_approval": "pending", "log": str(evidence / f"unreal-{action}-0.log")}
