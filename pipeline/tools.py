from __future__ import annotations

import hashlib
import os
import platform
import shutil
import stat
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

from .common import ROOT, StudioError, atomic_json, load_json, resource_lock


def tool_spec(tool: str, root: Path = ROOT) -> tuple[dict, dict]:
    record = load_json(root / "tools.lock.json")[tool]
    system = platform.system().lower()
    machine = platform.machine().lower()
    machine = {"amd64": "x86_64", "aarch64": "arm64"}.get(machine, machine)
    key = "darwin" if system == "darwin" and tool == "godot" else f"{system}-{machine}"
    if key not in record:
        raise StudioError(f"No pinned {tool} binary for {key}; set {tool.upper()}_BIN explicitly")
    return record, record[key]


def tool_binary(tool: str, root: Path = ROOT) -> Path:
    override = os.environ.get(f"{tool.upper()}_BIN")
    if override:
        path = Path(override).expanduser().resolve()
    else:
        record, spec = tool_spec(tool, root)
        if "executable" in spec:
            path = root / ".studio/tools" / tool / record["version"] / spec["executable"]
        else:
            path = Path("/Applications/Blender.app/Contents/MacOS/Blender")
    if not path.is_file() or not os.access(path, os.X_OK):
        raise StudioError(f"{tool} unavailable. Run `python3 studio.py tools fetch {tool}` "
                          f"or set {tool.upper()}_BIN to an executable")
    return path


def verified_download(spec: dict, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / Path(urlsplit(spec["url"]).path).name
    if target.exists():
        with target.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() == spec["sha256"]:
                return target
        raise StudioError(f"Cached archive checksum mismatch: {target}; inspect/remove it explicitly")
    fd, name = tempfile.mkstemp(prefix=".download-", dir=directory)
    temporary = Path(name)
    try:
        request = urllib.request.Request(spec["url"], headers={"User-Agent": "Novanode-Studio/0.1"})
        with os.fdopen(fd, "wb") as output, urllib.request.urlopen(request, timeout=90) as response:
            shutil.copyfileobj(response, output)
        with temporary.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != spec["sha256"]:
            raise StudioError(f"SHA-256 mismatch for {spec['url']}; refusing to extract")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def extract_zip(archive: Path, target: Path) -> None:
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            path = (target / info.filename).resolve()
            if not path.is_relative_to(target.resolve()):
                raise StudioError("Archive contains a path outside its destination")
            if stat.S_ISLNK(info.external_attr >> 16):
                raise StudioError("Unexpected symbolic link in tool ZIP")
        bundle.extractall(target)
        for info in bundle.infolist():
            if not info.is_dir():
                mode = (info.external_attr >> 16) & 0o777
                if mode:
                    (target / info.filename).chmod(mode)


def fetch_tool(tool: str, templates=False, root: Path = ROOT) -> dict:
    record, spec = tool_spec(tool, root)
    if tool == "blender" and platform.system() == "Darwin":
        raise StudioError(
            "Install Blender " + record["version"] + " from " + spec["url"]
            + " (SHA-256 " + spec["sha256"] + "). Then set BLENDER_BIN. "
            "This command does not mount disk images or change Applications."
        )
    with resource_lock("tool-downloads", root):
        destination = root / ".studio/tools" / tool / record["version"]
        executable = destination / spec["executable"]
        if not executable.exists():
            archive = verified_download(spec, root / ".studio/downloads")
            destination.mkdir(parents=True, exist_ok=True)
            if archive.name.endswith(".tar.xz"):
                with tarfile.open(archive) as bundle:
                    bundle.extractall(destination, filter="data")
            else:
                extract_zip(archive, destination)
            executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
        if templates:
            if tool != "godot":
                raise StudioError("Export templates are only applicable to Godot")
            target = root / ".studio/tools/godot/templates"
            target.mkdir(parents=True, exist_ok=True)
            marker = target / "manifest.json"
            names = ("linux_release.x86_64", "macos.zip")
            installed = load_json(marker) if marker.exists() else {}
            ready = (installed.get("version") == record["version"]
                     and installed.get("archive_sha256") == record["templates"]["sha256"])
            for name in names:
                path = target / name
                if not path.is_file():
                    ready = False
                elif ready:
                    with path.open("rb") as stream:
                        ready = hashlib.file_digest(stream, "sha256").hexdigest() == installed.get("files", {}).get(name)
            if not ready:
                archive = verified_download(record["templates"], root / ".studio/downloads")
                hashes = {}
                with zipfile.ZipFile(archive) as bundle:
                    for name in names:
                        with bundle.open(f"templates/{name}") as source, (target / name).open("wb") as output:
                            shutil.copyfileobj(source, output)
                        with (target / name).open("rb") as stream:
                            hashes[name] = hashlib.file_digest(stream, "sha256").hexdigest()
                atomic_json(marker, {"version": record["version"], "files": hashes,
                                     "archive_sha256": record["templates"]["sha256"]})
        return {"tool": tool, "version": record["version"], "executable": str(executable),
                "templates": templates}
