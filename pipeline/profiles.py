"""Read-only project selection and bounded metadata diagnostics, never a launch gate.

No native launcher/helper imports, subprocesses, network, or writes belong here.
Historical journals do not bind the engine/content snapshot and cannot approve a run.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import itertools
import os
from pathlib import Path
import re
import sys

from .common import ROOT, StudioError, config, load_json, project_path, utc_now

IDS = ("lab", "hero-sandbox")
MAX_METADATA_BYTES = 1_000_000
MAX_JOURNALS = 128
MAX_SOURCE_FILES = 256
MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_BINARY_BYTES = 256 * 1024 * 1024
HERO_SOURCE = "projects/hero-sandbox/NovanodeHeroes"
HERO_LAUNCHER = "projects/hero-sandbox/manage.py"
HERO_HELPER = ".studio/scripts/lyra_startup.py"
HERO_IDENTITY = {
    "project": ".studio/lyra/projects/LyraStarterGame/Lyra.uproject",
    "map": "/NovanodeHeroes/Maps/L_HeroSandbox_v2",
    "experience": "/NovanodeHeroes/Experiences/B_HeroSandbox_v2",
    "engine_version": "5.8.4",
}
SHA256 = re.compile(r"[0-9a-f]{64}")
JOB_ID = re.compile(r"[a-z][a-z0-9-]{0,95}")
SOURCE_IGNORED = {".git", "Binaries", "Intermediate", "Saved", "Content", "DerivedDataCache", "__pycache__"}
SOURCE_TYPES = {".cpp", ".h", ".cs", ".ini", ".uplugin"}


def _local_path(value: str, root: Path) -> Path:
    """Refuse symlink metadata, including links to other files inside the checkout."""
    path = project_path(value, root)
    current = root
    for part in Path(value).parts:
        current /= part
        if current.is_symlink():
            raise StudioError(f"Symlink metadata is not inspected: {value}")
    return path


def _metadata(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise StudioError("Metadata file missing or unsafe")
    if path.stat().st_size > MAX_METADATA_BYTES:
        raise StudioError("Metadata exceeds the diagnostic size limit")
    try:
        data = load_json(path)
    except RecursionError as exc:
        raise StudioError("Metadata nesting exceeds diagnostic limits") from exc
    if not isinstance(data, dict):
        raise StudioError("Metadata must be a JSON object")
    return data


def _configured(root: Path) -> tuple[dict, dict]:
    settings = config(root)
    studio = settings.get("studio")
    if not isinstance(studio, dict) or not isinstance(studio.get("project"), str):
        raise StudioError("studio.toml requires an explicit studio.project")
    project_path(studio["project"], root)
    profiles = settings.get("profiles", {})
    if not isinstance(profiles, dict) or set(profiles) != set(IDS):
        raise StudioError("studio.toml requires explicit profiles.lab and profiles.hero-sandbox")
    fields = {"label", "project", "map", "experience", "engine_version"}
    for name, row in profiles.items():
        if not isinstance(row, dict) or set(row) != fields or any(not isinstance(v, str) for v in row.values()):
            raise StudioError(f"Invalid project profile: {name}")
        if not row["label"] or not row["map"] or not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", row["engine_version"]):
            raise StudioError(f"Invalid label/engine version in profile {name}")
        if Path(row["project"]).suffix != ".uproject":
            raise StudioError(f"Profile {name} must select a .uproject descriptor")
        project_path(row["project"], root)
        for key in ("map", "experience"):
            if row[key] and not re.fullmatch(r"/(?:Game|NovanodeHeroes)/[A-Za-z0-9_/]+", row[key]):
                raise StudioError(f"Invalid {key} in profile {name}")
    projects = [row["project"] for row in profiles.values()]
    if len(set(projects)) != len(projects):
        raise StudioError("Project profiles must select different projects")
    return settings, profiles


def list_profiles(root: Path = ROOT) -> dict:
    settings, profiles = _configured(root)
    default = settings["studio"]["project"]
    return {
        "status": "configuration_only", "read_only": True, "default_project": default,
        "default_profile": next((name for name, row in profiles.items() if row["project"] == default), None),
        "profiles": [{"id": name, **profiles[name], "is_default": profiles[name]["project"] == default}
                     for name in IDS],
    }


def resolve(name: str | None = None, root: Path = ROOT) -> dict:
    listing = list_profiles(root)
    selected = name if name is not None else listing["default_profile"]
    if selected not in IDS:
        raise StudioError("Unknown/unmapped project profile; choose --profile lab or --profile hero-sandbox")
    return next(row for row in listing["profiles"] if row["id"] == selected)


def require_lab_adapter(profile: dict, root: Path = ROOT) -> None:
    """The legacy adapter still reads studio.project and has a fixed map/module."""
    settings = config(root)
    if (profile["id"] != "lab" or profile["project"] != settings["studio"]["project"]
            or profile["map"] != "/Game/Generated/Maps/NovanodeLab" or profile["experience"]
            or profile["engine_version"] != settings["unreal"]["version"]):
        raise StudioError("The lab adapter must match studio.project, unreal.version and its fixed lab map; "
                          "use projects status to inspect other profiles. No project was launched.")


def preview_hero(action: str, root: Path = ROOT) -> dict:
    profile = resolve("hero-sandbox", root)
    if any(profile[key] != value for key, value in HERO_IDENTITY.items()):
        raise StudioError("Hero profile differs from the fixed manage.py project/map/version; "
                          "review a launcher migration before using this preview")
    if action not in {"run", "editor"}:
        raise StudioError("Hero profile supports run/editor previews only; use the existing reviewed "
                          "projects/hero-sandbox/manage.py operations for native work")
    # This is a wrapper preview, not an unguarded Unreal argv or a new execution route.
    return {
        "status": "dry_run", "read_only": True, "profile": profile["id"],
        "project": str(_local_path(profile["project"], root)),
        "map": profile["map"], "experience": profile["experience"],
        "commands": [[sys.executable, str(_local_path(HERO_LAUNCHER, root)),
                      "play-v2" if action == "run" else "editor-v2"]],
        "execution_supported": False,
        "notice": "Preview only. manage.py retains its own fixed project/map, engine path and ignored local "
                  "helpers; its identity/ownership/content guards still apply. Check projects status first.",
    }


def _descriptor(profile: dict, root: Path) -> dict:
    try:
        path = _local_path(profile["project"], root)
        data = _metadata(path)
    except (StudioError, OSError):
        return {"status": "missing_or_invalid", "action": "Restore the selected descriptor; acquire licensed Lyra "
                "locally for Hero Lab. No engine or sample is downloaded by this command."}
    association = data.get("EngineAssociation")
    expected = ".".join(profile["engine_version"].split(".")[:2])
    modules = data.get("Modules")
    names = ({row.get("Name") for row in modules
              if isinstance(row, dict) and isinstance(row.get("Name"), str)}
             if isinstance(modules, list) else set())
    required = "NovanodeLab" if profile["id"] == "lab" else "LyraGame"
    compatible = association == expected and required in names
    return {
        "status": "metadata_compatible" if compatible else "incompatible",
        "engine_association_matches": association == expected,
        "required_module_present": required in names,
        "action": None if compatible else "Review the project/version/profile; do not migrate or launch automatically.",
        "native_verified": False,
    }


def _engine(profile: dict) -> dict:
    result = {"expected_version": profile["engine_version"], "configured_by": "UE_ROOT",
              "status": "not_configured", "native_verified": False}
    value = os.environ.get("UE_ROOT")
    if not value:
        return {**result, "action": "Set UE_ROOT to your already installed, licensed Linux engine root; "
                "no installation or EULA acceptance is automated."}
    ue = Path(value).expanduser().resolve()
    try:
        version_path = ue / "Engine/Build/Build.version"
        for path in (version_path, ue / "Engine/Binaries/Linux/UnrealEditor",
                     ue / "Engine/Build/BatchFiles/Linux/Build.sh", ue / "Engine/Build/BatchFiles/RunUAT.sh"):
            if not path.resolve().is_relative_to(ue):
                raise StudioError("Engine metadata/binary path escapes UE_ROOT")
        version = _metadata(version_path)
        numbers = [version.get(key) for key in ("MajorVersion", "MinorVersion", "PatchVersion")]
        if any(type(number) is not int or number < 0 for number in numbers):
            raise StudioError("Incomplete engine version metadata")
        observed = ".".join(map(str, numbers))
        expected = profile["engine_version"].split(".")
        result.update(root=str(ue), observed_version=observed,
                      build_version_sha256=hashlib.sha256(version_path.read_bytes()).hexdigest())
        if observed.split(".")[:len(expected)] != expected:
            return {**result, "status": "incompatible", "action": "UE_ROOT version differs from the selected "
                    "profile. Review the version; do not migrate automatically."}
        missing = [name for name in ("Engine/Binaries/Linux/UnrealEditor", "Engine/Build/BatchFiles/Linux/Build.sh",
                                    "Engine/Build/BatchFiles/RunUAT.sh")
                   if not (ue / name).is_file() or not os.access(ue / name, os.X_OK)]
        return {**result, "status": "metadata_compatible" if not missing else "incomplete_installation",
                "missing_executables": missing, "action": None if not missing else "Restore the licensed Linux installation."}
    except (StudioError, OSError):
        return {**result, "status": "missing_or_invalid", "action": "Check UE_ROOT and Engine/Build/Build.version; "
                "unsafe, malformed or oversized metadata is not inspected."}


def _resources(root: Path) -> dict:
    try:
        data = _metadata(_local_path("resources/hero-sandbox/catalog.json", root))
        items = data.get("items")
        if data.get("schema_version") != 1 or not isinstance(items, list) or len(items) > 128:
            raise StudioError("Invalid resource catalog")
        rows = []
        seen = set()
        for item in items:
            if (not isinstance(item, dict) or not isinstance(item.get("id"), str)
                    or not JOB_ID.fullmatch(item["id"]) or item["id"] in seen):
                raise StudioError("Invalid resource identity")
            seen.add(item["id"])
            pin = item.get("sha256")
            pinned = isinstance(pin, str) and bool(SHA256.fullmatch(pin))
            rows.append({"id": item["id"], "reviewed": item.get("review") == "reviewed_item", "pinned": pinned,
                         "review_hold": item.get("review") != "reviewed_item", "pin_hold": not pinned,
                         "ai_input_hold": item.get("ai_input") != "cc0_no_additional_restriction_found"})
        return {"status": "catalog_metadata_only", "items": rows, "native_import_verified": False,
                "notice": "Review, pin and AI-input holds are distinct. Static catalog labels do not verify import, "
                          "current download rights, or permission to upload assets to an AI service."}
    except (StudioError, OSError):
        return {"status": "missing_or_invalid", "items": [], "native_import_verified": False}


def _fingerprint(value: str, root: Path) -> dict[str, str]:
    folder = _local_path(value, root)
    if not folder.is_dir():
        raise StudioError("Owned source tree missing")
    hashes = {}
    total = 0
    # Bound traversal, not just reads; do not follow or hash any symlink target.
    visited = 0
    for directory, dirs, files in os.walk(folder, followlinks=False):
        base = Path(directory)
        visited += len(dirs) + len(files)
        if visited > MAX_SOURCE_FILES * 4:
            raise StudioError("Source tree exceeds the diagnostic entry limit")
        for name in list(dirs):
            if (base / name).is_symlink():
                raise StudioError("Symlink in owned source tree")
            if name in SOURCE_IGNORED:
                dirs.remove(name)
        for name in files:
            path = base / name
            if path.is_symlink() or not path.is_file():
                raise StudioError("Unsafe owned source file")
            if any(part.startswith(".env") for part in path.relative_to(folder).parts):
                raise StudioError("Credential/environment paths cannot be fingerprinted")
            if path.suffix not in SOURCE_TYPES:
                raise StudioError("Unrecognized file type in owned source tree; inspect locally before hashing")
            total += path.stat().st_size
            if len(hashes) >= MAX_SOURCE_FILES or total > MAX_SOURCE_BYTES:
                raise StudioError("Source hashes exceed diagnostic limits")
            with path.open("rb") as stream:
                hashes[path.relative_to(folder).as_posix()] = hashlib.file_digest(stream, "sha256").hexdigest()
    if not hashes:
        raise StudioError("Owned source tree is empty")
    return hashes


def _finished_at(row: dict) -> str | None:
    value = row.get("finished_at")
    if not isinstance(value, str):
        return None
    try:
        date = datetime.fromisoformat(value)
        if date.tzinfo is None:
            return None
        return date.astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError):
        return None


def _hashes(value, limit=MAX_SOURCE_FILES) -> bool:
    return (isinstance(value, dict) and 0 < len(value) <= limit
            and all(isinstance(key, str) and key and not Path(key).is_absolute() and ".." not in Path(key).parts
                    and isinstance(digest, str) and SHA256.fullmatch(digest) for key, digest in value.items()))


def _historical_success(row: dict, profile: dict) -> bool:
    """Validate claimed completion, without upgrading it to a current verification gate."""
    operation, summary = row.get("operation"), row.get("summary")
    if not isinstance(operation, str) or not isinstance(summary, dict):
        return False
    if any(type(summary.get(key)) is not int or summary[key] != 0
           for key in ("fatal_count", "error_severity_count")):
        return False
    if operation == "build":
        binary_hash = row.get("native_module_sha256")
        return (_hashes(row.get("source_sha256")) and isinstance(binary_hash, str)
                and bool(SHA256.fullmatch(binary_hash)))
    if summary.get("normal_exit_marker") is not True:
        return False
    if operation in {"prepare-v2", "validate-v2"}:
        data = row.get("preparation")
        return (isinstance(data, dict) and data.get("state") == "prepared"
                and data.get("map") == profile["map"] and _hashes(data.get("generated_sha256"), 1024)
                and "Maps/L_HeroSandbox_v2.umap" in data["generated_sha256"])
    if operation == "smoke-v2":
        return isinstance(row.get("smoke"), dict) and row["smoke"].get("passed") is True
    if operation == "probe-v2-rendered":
        data = row.get("presentation")
        return (isinstance(data, dict)
                and data.get("state") == "presentation_structure_observed_not_visual_approval"
                and data.get("usable_character_body_present") is True
                and data.get("pawn_possessed") is True
                and data.get("camera_view_target_is_pawn") is True
                and data.get("rendered_probe_requested") is True
                and type(data.get("recently_rendered_character_body_components")) is int
                and data["recently_rendered_character_body_components"] >= 1)
    return True


def _hero_history(profile: dict, root: Path) -> dict:
    gates = {key: {"status": "unknown"} for key in
             ("native_build", "prepared_assets", "standalone_gameplay", "rendered_body")}
    result = {"coverage": "complete", "unresolved_job_scan_complete": False,
              "unresolved_jobs": [], "blocked_jobs": [], "unqualified_completions": [], "invalid_journals": [],
              "last_successful_build": None, "gates": gates,
              "notice": "Journals lack a complete engine/content snapshot binding. Even matching source/binary "
                        "hashes remain historical, not current native approval. No logs or PIDs are inspected."}
    if any(profile[key] != value for key, value in HERO_IDENTITY.items()):
        return {**result, "coverage": "profile_identity_mismatch",
                "action": "Historical Hero journals belong to the fixed manage.py profile, not these modified settings."}
    try:
        folder = _local_path(".studio/evidence", root)
        paths = list(itertools.islice(folder.glob("hero-sandbox-job-*.json"), MAX_JOURNALS + 1))
        if len(paths) > MAX_JOURNALS:
            result.update(coverage="limit_exceeded", action="Review journal inventory; no partial success is promoted.")
            return result
        records = []
        for path in sorted(paths):
            try:
                row = _metadata(_local_path(path.relative_to(root).as_posix(), root))
                job = row.get("job_id")
                if (not isinstance(job, str) or not JOB_ID.fullmatch(job)
                        or path.name != f"hero-sandbox-job-{job}.json"):
                    raise StudioError("Journal identity mismatch")
                state = row.get("state")
                if not isinstance(state, str) or state not in {"completed", "blocked"}:
                    result["unresolved_jobs"].append({"job_id": job, "state": state if state in
                        ("reserved", "running_unknown", "running", "unknown", "interrupted") else "unrecognized",
                        "reconciliation_required": True})
                    continue
                if state == "blocked":
                    result["blocked_jobs"].append({"job_id": job,
                        "exit_code": row.get("exit_code") if type(row.get("exit_code")) is int else None})
                    continue
                finished = _finished_at(row)
                if type(row.get("exit_code")) is not int or row["exit_code"] != 0 or not finished:
                    raise StudioError("Contradictory or undated completion")
                if _historical_success(row, profile):
                    records.append((finished, job, row))
                else:
                    result["unqualified_completions"].append({"job_id": job, "reason": "completion_checks_not_met"})
            except (StudioError, OSError):
                result["invalid_journals"].append(path.name if JOB_ID.fullmatch(path.stem.removeprefix("hero-sandbox-job-"))
                                                   else "unrecognized_journal_filename")
        records.sort(key=lambda item: (item[0], item[1]), reverse=True)
        result["unresolved_job_scan_complete"] = not result["invalid_journals"]
        for key, operations in (("prepared_assets", {"prepare-v2", "validate-v2"}),
                                ("standalone_gameplay", {"smoke-v2"}), ("rendered_body", {"probe-v2-rendered"})):
            candidate = next((item for item in records if item[2].get("operation") in operations), None)
            if candidate:
                gates[key] = {"status": "historical_unbound", "job_id": candidate[1], "finished_at": candidate[0]}
        builds = [item for item in records if item[2].get("operation") == "build"]
        if builds:
            finished, job, row = builds[0]
            identity = {"job_id": job, "finished_at": finished, "status": "historical_unbound",
                        "source_matches": None, "staged_source_matches": None, "binary_matches": None,
                        "engine_binding": "unrecorded", "content_binding": "not_assessed", "current_verified": False}
            try:
                authored = _fingerprint(HERO_SOURCE, root)
                stage = str(Path(profile["project"]).parent / "Plugins/NovanodeHeroes")
                staged = _fingerprint(stage, root)
                module = _local_path(stage + "/Binaries/Linux/libUnrealEditor-NovanodeHeroes.so", root)
                if not module.is_file() or module.stat().st_size > MAX_BINARY_BYTES:
                    raise StudioError("Owned module missing or oversized")
                with module.open("rb") as stream:
                    elf = stream.read(4) == b"\x7fELF"
                    stream.seek(0)
                    binary_hash = hashlib.file_digest(stream, "sha256").hexdigest()
                identity.update(source_matches=row.get("source_sha256") == authored,
                                staged_source_matches=staged == authored,
                                binary_matches=elf and row.get("native_module_sha256") == binary_hash)
                if not all(identity[key] for key in ("source_matches", "staged_source_matches", "binary_matches")):
                    identity["status"] = "stale"
            except (StudioError, OSError):
                identity["status"] = "identity_unavailable"
            result["last_successful_build"] = identity
            gates["native_build"] = {**identity}
        if result["invalid_journals"]:
            result["coverage"] = "invalid_metadata"
        return result
    except (StudioError, OSError):
        return {**result, "coverage": "unavailable", "action": "Inspect the local journal directory; no holds were cleared."}


def status(name: str | None = None, root: Path = ROOT) -> dict:
    profile = resolve(name, root)
    listing = list_profiles(root)
    gates = {key: {"status": "not_assessed_no_bound_evidence"} for key in
             ("native_build", "prepared_assets", "standalone_gameplay", "rendered_body")}
    result = {
        "status": "diagnostic_only", "read_only": True, "target": "linux", "observed_at": utc_now(),
        "profile": profile, "default_project": listing["default_project"],
        "default_profile": listing["default_profile"], "project": _descriptor(profile, root),
        "engine": _engine(profile), "execution_readiness": "not_assessed",
        "human_approval": "pending", "gates": gates,
        "scope": "Metadata and local hashes only; not a native, gameplay, art, FPS or package test.",
    }
    if profile["id"] == "hero-sandbox":
        history = _hero_history(profile, root)
        result["history"] = {key: value for key, value in history.items() if key != "gates"}
        gates.update(history["gates"])
        result["resources"] = _resources(root)
        try:
            helper_present = _local_path(HERO_HELPER, root).is_file()
            launcher_present = _local_path(HERO_LAUNCHER, root).is_file()
        except (StudioError, OSError):
            helper_present = launcher_present = False
        result["launcher"] = {"path": HERO_LAUNCHER, "present": launcher_present,
                              "local_entry_helper_present": helper_present, "portable": False,
                              "disabled_operations": ["text-capture"],
                              "action": "Use existing manage.py only after its own guards pass. Its engine path and "
                                        "transitive ignored helpers are not validated/migrated here."}
    else:
        result["history"] = {"last_successful_build": None, "notice": "The legacy lab adapter has no source-bound "
                             "build journal for this diagnostic. Old log files are not ingested or promoted."}
        result["resources"] = {"status": "not_applicable"}
        result["launcher"] = {"path": "studio.py unreal", "portable": True,
                              "action": "Existing lab adapter; native operations still require UE_ROOT and their own checks."}
    gates.update({key: {"status": "not_verified"} for key in ("multiplayer", "performance", "package")})
    gates["visual_controls"] = {"status": "human_review_pending"}
    return result
