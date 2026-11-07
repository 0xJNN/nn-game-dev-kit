from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys

from . import engines, models, profiles, unreal
from .assets import validate_asset
from .common import ROOT, StudioError, atomic_json, config, load_json, project_path
from .ledger import Ledger
from .tasks import read_contract, run_task, task_context
from .tools import fetch_tool


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description="Novanode Studio: local, bounded production tools")
    commands = cli.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="Report availability; --profile selects read-only project metadata")
    doctor.add_argument("--profile", choices=profiles.IDS)
    projects = commands.add_parser("projects", help="Read-only project profiles, not model/agent profiles")
    project_actions = projects.add_subparsers(dest="action", required=True)
    project_actions.add_parser("list")
    project_status = project_actions.add_parser("status")
    project_status.add_argument("--profile", choices=profiles.IDS, help="Default: match studio.project")
    commands.add_parser("test", help="Run the dependency-free Python tests")
    run = commands.add_parser("run", help="Preview/launch the primary Unreal Linux experience")
    run.add_argument("--execute", action="store_true")
    run.add_argument("--profile", choices=profiles.IDS)
    hero = commands.add_parser("hero", help="Native Hero Training lobby (separate from legacy pilots)")
    hero_actions = hero.add_subparsers(dest="action", required=True)
    play = hero_actions.add_parser("play", help="Preview the manual lobby launch; --execute opens the game")
    play.add_argument("--execute", action="store_true", help="Open a graphical Offline game; close its window to exit")
    ue = commands.add_parser("unreal", help="Linux Unreal source, build, and verification gates")
    ue_actions = ue.add_subparsers(dest="action", required=True)
    for name in ("doctor", "validate"):
        ue_actions.add_parser(name).add_argument("--profile", choices=profiles.IDS)
    for name in ("build", "prepare", "test", "run", "editor", "package", "smoke"):
        operation = ue_actions.add_parser(name)
        operation.add_argument("--execute", action="store_true", help="Execute against your installed UE_ROOT (default: preview)")
        operation.add_argument("--profile", choices=profiles.IDS)
    model = commands.add_parser("models", help="Research metadata, opt-in profiles, and local serving plans")
    model_actions = model.add_subparsers(dest="action", required=True)
    model_actions.add_parser("list")
    model_actions.add_parser("refresh-free", help="Fetch public OpenRouter metadata; never calls a model")
    for name in ("plan", "fetch", "serve", "probe"):
        operation = model_actions.add_parser(name)
        operation.add_argument("model")
        if name in {"plan", "serve"}:
            operation.add_argument("--mode", choices=["solo", "editor"], default="editor")
        if name != "plan":
            operation.add_argument("--execute", action="store_true")
    profile = model_actions.add_parser("config", help="Write an inactive OpenCode V2 example under .studio/opencode/")
    profile.add_argument("--profile", choices=["free", "local"], required=True)
    profile.add_argument("--local-model", default="qwen35-small")
    tools = commands.add_parser("tools").add_subparsers(dest="action", required=True)
    fetch = tools.add_parser("fetch", help="Download checksum-verified portable tools into .studio")
    fetch.add_argument("tool", choices=["godot", "blender"])
    fetch.add_argument("--templates", action="store_true", help="Also download ~1.3 GB export templates")
    task = commands.add_parser("task").add_subparsers(dest="action", required=True)
    for name in ("validate", "context", "run"):
        sub = task.add_parser(name)
        sub.add_argument("contract")
        if name == "run":
            sub.add_argument("--execute", action="store_true", help="Run reviewed local argv (not a sandbox)")
    assets = commands.add_parser("assets").add_subparsers(dest="action", required=True)
    assets.add_parser("build", help="Build and validate the procedural Blender bench")
    validate = assets.add_parser("validate")
    validate.add_argument("manifest")
    godot = commands.add_parser("godot").add_subparsers(dest="action", required=True)
    godot.add_parser("run", help="Open the demo interactively (human-controlled session)")
    test = godot.add_parser("test")
    test.add_argument("--output", default=".studio/evidence/gold-path.json")
    capture = godot.add_parser("capture", help="Requires a graphical session")
    capture.add_argument("--output", default=".studio/evidence/lab.png")
    export = godot.add_parser("export", help="Internal artifact; not a release approval")
    export.add_argument("--platform", choices=["linux", "macos"], required=True)
    export.add_argument("--smoke", action="store_true", help="Launch and test the native packaged build")
    jobs = commands.add_parser("jobs").add_subparsers(dest="action", required=True)
    jobs.add_parser("report")
    reserve = jobs.add_parser("reserve")
    reserve.add_argument("--key", required=True)
    reserve.add_argument("--task", default=os.environ.get("NOVANODE_TASK_ID"))
    reserve.add_argument("--provider", required=True)
    reserve.add_argument("--operation", required=True)
    reserve.add_argument("--max-cost", required=True)
    get = jobs.add_parser("get")
    get.add_argument("key")
    attach = jobs.add_parser("attach")
    attach.add_argument("key")
    attach.add_argument("--job-id", required=True)
    settle = jobs.add_parser("settle")
    settle.add_argument("key")
    settle.add_argument("--actual-cost", required=True)
    settle.add_argument("--outcome", choices=["accepted", "rejected", "failed", "cancelled"], required=True)
    settle.add_argument("--receipt", required=True, help="Project-relative JSON receipt; do not include secrets")
    return cli


def job_command(args):
    budgets = config()["budgets"]
    ledger = Ledger(ROOT / ".studio/ledger.sqlite3", budgets["total_usd"], budgets["per_task_usd"])
    try:
        if args.action == "reserve":
            if not args.task:
                raise StudioError("Supply --task or run under a task contract")
            return ledger.reserve(args.key, args.task, args.provider, args.operation, args.max_cost,
                                  os.environ.get("NOVANODE_TASK_BUDGET_USD"))
        if args.action == "attach":
            return ledger.attach(args.key, args.job_id)
        if args.action == "settle":
            source = project_path(args.receipt)
            if source.stat().st_size > 1_000_000:
                raise StudioError("Receipt exceeds 1 MB; store only the relevant billing evidence")
            value = load_json(source)
            digest = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
            destination = ROOT / ".studio/receipts" / f"{digest}.json"
            atomic_json(destination, value)
            usage = value.get("usage") if isinstance(value, dict) else None
            return ledger.settle(args.key, args.actual_cost, args.outcome,
                                 str(destination.relative_to(ROOT)), usage=usage)
        if args.action == "get":
            return ledger.get(args.key)
        return ledger.report()
    finally:
        ledger.close()


def project_unreal(action: str, execute=False, profile=None):
    if profile is not None:
        selected = profiles.resolve(profile)
        if action == "doctor":
            return profiles.status(profile)
        if selected["id"] == "hero-sandbox":
            if execute:
                raise StudioError("Hero profile execution is not migrated to studio.py. No engine started; "
                                  "use the existing reviewed projects/hero-sandbox/manage.py launcher.")
            return profiles.preview_hero(action)
        profiles.require_lab_adapter(selected)
    if action == "doctor":
        return unreal.doctor()
    if action == "validate":
        return unreal.validate_source()
    result = unreal.run(action, execute)
    if profile is not None and isinstance(result, dict):
        result.update(profile=profile, project=str(project_path(selected["project"])),
                      map=selected["map"], experience=selected["experience"] or None)
    return result


def dispatch(args):
    if args.command == "hero":
        from .hero_play import play
        return play(args.execute)
    if args.command == "projects":
        return profiles.list_profiles() if args.action == "list" else profiles.status(args.profile)
    if args.command == "doctor":
        if args.profile is not None:
            return profiles.status(args.profile)
        tools = {}
        for tool in ("blender",):
            try:
                tools[tool] = {"available": True, "path": str(engines.checked_binary(tool))}
            except (StudioError, OSError, subprocess.TimeoutExpired) as exc:
                tools[tool] = {"available": False, "reason": str(exc)}
        return {"python": sys.version.split()[0], "root": str(ROOT), "tools": tools,
                "unreal": unreal.doctor(), "paid_adapters": "disabled", "macos": "deferred"}
    if args.command == "run":
        return project_unreal("run", args.execute, args.profile)
    if args.command == "unreal":
        return project_unreal(args.action, getattr(args, "execute", False), args.profile)
    if args.command == "models":
        if args.action == "list":
            return load_json(ROOT / "models.lock.json")
        if args.action == "refresh-free":
            return models.refresh_free()
        if args.action == "plan":
            return models.plan(args.model, args.mode)
        if args.action == "fetch":
            return models.fetch(args.model, args.execute)
        if args.action == "serve":
            return models.serve(args.model, args.mode, args.execute)
        if args.action == "probe":
            return models.probe(args.model, args.execute)
        profile = models.opencode_profile(args.profile, args.local_model)
        output = ROOT / ".studio/opencode" / f"{args.profile}.json"
        atomic_json(output, profile)
        return {"status": "inactive_profile_written", "path": str(output),
                "notice": "Review before copying to project opencode.json. No global config or credentials changed."}
    if args.command == "test":
        return subprocess.call([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ROOT)
    if args.command == "tools":
        return fetch_tool(args.tool, args.templates)
    if args.command == "task":
        contract = project_path(args.contract)
        if args.action == "run":
            return run_task(contract, args.execute)
        task = read_contract(contract)
        if args.action == "context":
            print(task_context(task), end="")
            return 0
        return {"status": "valid", "task_id": task["id"]}
    if args.command == "assets":
        if args.action == "build":
            return engines.build_asset()
        return validate_asset(project_path(args.manifest))
    if args.command == "godot":
        if args.action == "test":
            return engines.godot_test(args.output)
        if args.action == "capture":
            return engines.capture(args.output)
        if args.action == "export":
            return engines.export(args.platform, args.smoke)
        binary = engines.checked_binary("godot")
        with engines.resource_lock("godot-lab"):
            engines.import_project(binary)
            return subprocess.call([str(binary), "--path", str(ROOT / config()["studio"]["legacy_godot_project"])])
    return job_command(args)


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        result = dispatch(args)
        if isinstance(result, int):
            return result
        print(json.dumps(result, indent=2, sort_keys=True))
        if args.command == "task" and args.action == "run":
            return 0 if result["status"] in {"dry_run", "machine_verified"} else 1
        return 0
    except KeyboardInterrupt:
        print("Interrupted; owned command processes stopped. Check the run journal.", file=sys.stderr)
        return 130
    except (StudioError, OSError, ValueError, sqlite3.Error, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}), file=sys.stderr)
        return 1
