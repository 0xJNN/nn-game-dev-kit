"""Manual native lobby launcher. No build, asset preparation or unattended probe."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import uuid

from .common import ROOT, StudioError, atomic_json, load_json, resource_lock, utc_now

ENGINE = Path("/run/media/d/SEARCHX_WORK/Unreal/engines/5.8.4")
LOBBY = "/Game/System/FrontEnd/Maps/L_LyraFrontEnd"
ENVIRONMENT = {"UE_SharedDataCachePath": "None", "UE-SharedDataCachePath": "None"}
NOTICE = ("Manual UI/visual approval pending. Melee/Mage still use shooter PawnData; "
          "hero combat/items and an Easy bot profile are not integrated.")


def command(root: Path, engine: Path) -> list[str]:
    root, engine = root.resolve(), engine.resolve()
    overrides = ",".join((
        "[OnlineSubsystem]:DefaultPlatformService=Null",
        "[OnlineServices]:DefaultServices=Null",
        "[/Script/AndroidFileServerEditor.AndroidFileServerRuntimeSettings]:bEnablePlugin=False",
        "[/Script/AndroidFileServerEditor.AndroidFileServerRuntimeSettings]:bAllowNetworkConnection=False",
        "[/Script/PythonScriptPlugin.PythonScriptPluginSettings]:bRemoteExecution=False",
        "[/Script/EngineSettings.GameMapsSettings]:GameDefaultMap=" + LOBBY,
    ))
    return [str(engine / "Engine/Binaries/Linux/UnrealEditor"),
            str(root / ".studio/lyra/projects/LyraStarterGame/Lyra.uproject"), LOBBY,
            "-game", "-fullscreen", "-DPCVars=r.FullScreenMode=1", "-NovanodeNativeFrontend",
            "-EnablePlugins=NovanodeTraining,PythonScriptPlugin,EditorScriptingUtilities",
            "-DisablePython", "-nop4", "-nosplash", "-NoIni", "-NoEOS", "-NoEpicPortal",
            "-RCWebControlDisable", "-RCProtocolsDisable", "-ini:Engine:" + overrides]


def active_editors(proc: Path = Path("/proc")) -> list[int]:
    """Read process names only, not user arguments or environments."""
    found = []
    for path in proc.iterdir():
        if not path.name.isdecimal():
            continue
        try:
            if path.stat().st_uid != os.getuid():
                continue
            name = (path / "comm").read_text().strip()
        except FileNotFoundError:
            continue  # Exited during enumeration.
        if name.startswith(("UnrealEditor", "UE4Editor", "Lyra")):
            found.append(int(path.name))
    return sorted(found)


def prerequisites(root: Path, argv: list[str]) -> None:
    if sys.platform != "linux":
        raise StudioError("This installed Hero Training launcher supports Linux only")
    stage = root / ".studio/lyra/projects/LyraStarterGame/Plugins/GameFeatures/NovanodeTraining"
    required = [Path(argv[0]), Path(argv[1]), stage / "NovanodeTraining.uplugin",
                stage / "Binaries/Linux/libUnrealEditor-NovanodeTraining.so",
                stage / "Binaries/Linux/UnrealEditor.modules",
                root / ".studio/lyra/projects/LyraStarterGame/Content/System/FrontEnd/Maps/L_LyraFrontEnd.umap",
                stage / "Content/Maps/L_HeroTraining.umap",
                stage / "Content/Experiences/DA_HeroTraining.uasset"]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise StudioError("Missing installed Hero Training files (no automatic build/download): " + ", ".join(missing))
    if not os.access(argv[0], os.X_OK):
        raise StudioError("UnrealEditor is not executable")
    for path in (root / ".studio/evidence").glob("hero-*-job-*.json"):
        if load_json(path).get("state") in {"reserved", "running_unknown", "outcome_unknown"}:
            raise StudioError("Unfinished native job; reconcile, do not retry: " + path.name)
    if active_editors():
        raise StudioError("An Unreal/Lyra session is already open. Close it normally before playing.")
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        raise StudioError("Run --execute from a terminal inside your graphical desktop session")
    try:
        gpu = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                             check=True, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        raise StudioError("Cannot confirm GPU memory with nvidia-smi; no game started") from exc
    try:
        free = int(gpu.stdout.splitlines()[0])
    except (ValueError, IndexError) as exc:
        raise StudioError("Cannot confirm available GPU memory; no game started") from exc
    if free < 4096:
        raise StudioError("Less than 4096 MiB VRAM free; no game started. Existing services were not stopped.")


def play(execute=False, root: Path = ROOT, engine: Path = ENGINE) -> dict:
    root = root.resolve()
    argv = command(root, engine)
    if not execute:
        return {"status": "preview", "cwd": str(root), "command": argv,
                "environment_overrides": dict(ENVIRONMENT), "notice": NOTICE,
                "next": "python3 studio.py hero play --execute"}
    with resource_lock("integrator", root), resource_lock("unreal-editor", root):
        prerequisites(root, argv)
        job = "play-" + uuid.uuid4().hex[:12]
        receipt = root / ".studio/evidence" / f"hero-native-manual-job-{job}.json"
        folder = root / ".studio/builds/hero-native-manual" / job
        folder.mkdir(parents=True, exist_ok=False)
        if receipt.exists():
            raise StudioError("Manual job collision; preserve the existing receipt")
        argv.append("-AbsLog=" + str(folder / "engine.log"))
        row = {"job_id": job, "operation": "manual-native-lobby", "state": "reserved", "command": argv,
               "started_at": utc_now(), "exit_code": None, "human_approval": "pending",
               "gameplay_verified": False, "notice": NOTICE}
        atomic_json(receipt, row)
        print(f"Opening Hero Training. Close the game window to exit. Receipt: {receipt}", flush=True)
        print(NOTICE, flush=True)
        child = None
        try:
            with (folder / "console.log").open("xb") as output:
                (folder / "console.log").chmod(0o600)
                child = subprocess.Popen(argv, cwd=root, env={**os.environ, **ENVIRONMENT},
                                         stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                                         start_new_session=True)
                row.update(state="running_unknown", pid=child.pid)
                atomic_json(receipt, row)  # PID persists even if start-time inspection fails.
                try:
                    row["process_start_ticks"] = Path(f"/proc/{child.pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
                except FileNotFoundError:
                    pass  # A very short-lived child is still reaped below.
                atomic_json(receipt, row)
                code = child.wait()
        except (Exception, KeyboardInterrupt) as exc:
            code = child.poll() if child is not None else None
            # An absent PID or interrupted wait never invents a native exit.
            row.update(state="blocked" if code is not None or (child is None and isinstance(exc, OSError)) else "outcome_unknown",
                       exit_code=code, observed_at=utc_now())
            atomic_json(receipt, row)
            raise StudioError(f"Manual launch interrupted or unavailable; close its window normally if open. "
                              f"Review {receipt} before retrying. No stop signal sent.") from exc
        row.update(state="completed" if code == 0 else "blocked", exit_code=code, finished_at=utc_now())
        atomic_json(receipt, row)
        if code != 0:
            raise StudioError(f"Game exited with code {code}; inspect {receipt}. No automatic retry.")
        return {**row, "receipt": str(receipt)}
