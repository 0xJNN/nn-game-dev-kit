from __future__ import annotations

import platform
import re
import subprocess
from pathlib import Path

from .assets import validate_asset
from .common import ROOT, StudioError, config, load_json, resource_lock
from .process import run_process
from .tools import extract_zip, tool_binary


def evidence_path(value: str, root: Path = ROOT) -> Path:
    path = Path(value)
    path = (root / path).resolve() if not path.is_absolute() else path.resolve()
    if not path.is_relative_to(root.resolve()):
        raise StudioError("Evidence must stay inside the project checkout")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def checked_binary(tool: str, root: Path = ROOT) -> Path:
    binary = tool_binary(tool, root)
    version = load_json(root / "tools.lock.json")[tool]["version"]
    result = subprocess.run([str(binary), "--version"], capture_output=True, text=True, timeout=15)
    first = result.stdout.splitlines()[0] if result.stdout else ""
    prefix = f"Blender {version}" if tool == "blender" else version + "."
    if result.returncode or not (first == prefix or first.startswith(prefix)):
        raise StudioError(f"Expected pinned {tool} {version}; got {first!r}")
    return binary


def checked_run(argv: list[str], timeout: int, log: Path, root: Path = ROOT) -> dict:
    result = run_process(argv, root, timeout, log)
    text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    if (result["exit_code"] != 0 or result["reason"] != "completed"
            or re.search(r"(?m)^(?:SCRIPT ERROR|ERROR):", text)):
        raise StudioError(f"Command failed ({result['reason']}, exit {result['exit_code']}). "
                          f"See {log}\n{text[-1800:]}")
    return result


def import_project(binary: Path, root: Path = ROOT):
    project = root / config(root)["studio"]["legacy_godot_project"]
    checked_run([str(binary), "--headless", "--path", str(project), "--editor", "--import"],
                120, root / ".studio/evidence/import.log", root)


def godot_test(output: str, root: Path = ROOT) -> dict:
    binary = checked_binary("godot", root)
    path = evidence_path(output, root)
    with resource_lock("godot-lab", root):
        import_project(binary, root)
        path.unlink(missing_ok=True)
        project = root / config(root)["studio"]["legacy_godot_project"]
        checked_run([str(binary), "--headless", "--path", str(project), "--script",
                     "res://tests/gold_path.gd", "--", f"--report={path}"],
                    60, path.with_suffix(".log"), root)
        report = load_json(path)
        checks = report.get("checks")
        if (report.get("status") != "passed" or not isinstance(checks, list) or not checks
                or not all(isinstance(check, dict) and check.get("passed") is True for check in checks)):
            raise StudioError(f"Gold path failed; see {path}")
        return {"status": "machine_verified", "checks": len(report["checks"]),
                "evidence": str(path), "human_approval": "pending"}


def build_asset(root: Path = ROOT) -> dict:
    binary = checked_binary("blender", root)
    # Background process has a factory-startup scene; no interactive file is touched.
    with resource_lock("blender-bench", root):
        checked_run([str(binary), "--background", "--factory-startup", "--disable-autoexec",
                     "--python-exit-code", "1", "--python", str(root / "scripts/blender/build_bench.py"),
                     "--", "--root", str(root)],
                    120, root / ".studio/evidence/blender-build.log", root)
        return validate_asset(root / "projects/lab/assets/generated/bench.manifest.json", root)


def capture(output: str, root: Path = ROOT) -> dict:
    binary = checked_binary("godot", root)
    path = evidence_path(output, root)
    with resource_lock("godot-lab", root):
        import_project(binary, root)
        path.unlink(missing_ok=True)
        project = root / config(root)["studio"]["legacy_godot_project"]
        checked_run([str(binary), "--path", str(project), "--rendering-method", "gl_compatibility",
                     "--", f"--capture={path}"], 60, path.with_suffix(".log"), root)
        if not path.is_file() or path.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            raise StudioError("No valid fresh screenshot produced")
    return {"status": "captured_not_approved", "evidence": str(path), "human_approval": "pending"}


def export(platform_name: str, smoke: bool, root: Path = ROOT) -> dict:
    binary = checked_binary("godot", root)
    native = "macos" if platform.system() == "Darwin" else "linux"
    if smoke and native != platform_name:
        raise StudioError("Native startup verification requires a matching host OS")
    manifest = root / "projects/lab/assets/generated/bench.manifest.json"
    validate_asset(manifest, root)
    preset = "Linux" if platform_name == "linux" else "macOS"
    template = "linux_release.x86_64" if platform_name == "linux" else "macos.zip"
    if not (root / ".studio/tools/godot/templates" / template).is_file():
        raise StudioError("Export templates missing. Run `python3 studio.py tools fetch godot --templates`")
    filename = "NovanodeLab.x86_64" if platform_name == "linux" else "NovanodeLab.zip"
    output = root / ".studio/builds" / platform_name / filename
    output.parent.mkdir(parents=True, exist_ok=True)
    with resource_lock("godot-lab", root):
        import_project(binary, root)
        output.unlink(missing_ok=True)
        project = root / config(root)["studio"]["legacy_godot_project"]
        checked_run([str(binary), "--headless", "--path", str(project), "--export-release", preset,
                     str(output)], 180, output.with_suffix(".export.log"), root)
        if not output.is_file() or not output.stat().st_size:
            raise StudioError("Export reported success but no build exists")
        report = {"artifact": str(output), "status": "built_not_native_verified",
                  "human_approval": "pending", "distribution": (
                      "internal_adhoc_not_notarized" if platform_name == "macos" else "internal_unsigned"
                  )}
        if smoke:
            executable = output
            if platform_name == "macos":
                extract_zip(output, output.parent)
                executables = list(output.parent.glob("*.app/Contents/MacOS/*"))
                if len(executables) != 1:
                    raise StudioError("Expected exactly one macOS application executable")
                executable = executables[0]
            executable.chmod(executable.stat().st_mode | 0o100)
            evidence = output.parent / "startup.json"
            evidence.unlink(missing_ok=True)
            checked_run([str(executable), "--headless", "--", f"--smoke-report={evidence}"],
                        60, output.parent / "startup.log", root)
            startup = load_json(evidence)
            if startup.get("status") != "passed" or not startup.get("generated_bench_loaded"):
                raise StudioError("Packaged normal-startup check failed")
            report.update(status="machine_verified", evidence=str(evidence))
        return report
