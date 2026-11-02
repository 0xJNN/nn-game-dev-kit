"""CI-only convenience: run the pinned Blender; on macOS mount a read-only vendor DMG.

No app is installed into Applications. Native macOS execution requires a macOS runner.
"""
import os
import platform
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.common import ROOT, resource_lock
from pipeline.engines import build_asset
from pipeline.tools import fetch_tool, tool_spec, verified_download


def main():
    if platform.system() != "Darwin":
        fetch_tool("blender")
        print(build_asset())
        return
    _, spec = tool_spec("blender")
    archive = verified_download(spec, ROOT / ".studio/downloads")
    mount = ROOT / ".studio/blender-ci-mount"
    mount.mkdir(exist_ok=True)
    with resource_lock("blender-ci-mount"):
        subprocess.run(["hdiutil", "attach", str(archive), "-readonly", "-nobrowse",
                        "-mountpoint", str(mount)], check=True, timeout=120)
        previous = os.environ.get("BLENDER_BIN")
        try:
            os.environ["BLENDER_BIN"] = str(mount / "Blender.app/Contents/MacOS/Blender")
            print(build_asset())
        finally:
            if previous is None:
                os.environ.pop("BLENDER_BIN", None)
            else:
                os.environ["BLENDER_BIN"] = previous
            subprocess.run(["hdiutil", "detach", str(mount)], check=True, timeout=60)


if __name__ == "__main__":
    main()
