from __future__ import annotations

import os
import selectors
import signal
import subprocess
import time
from pathlib import Path

from .common import StudioError


def run_process(argv: list[str], cwd: Path, timeout: float, log: Path,
                env: dict | None = None, max_log_bytes: int = 4_000_000) -> dict:
    """Bound wall time and log size; terminate the owned process group, including helpers."""
    if timeout <= 0:
        return {"exit_code": None, "reason": "deadline", "seconds": 0}
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    process = None
    reason = "completed"
    try:
        with log.open("wb") as output, selectors.DefaultSelector() as selector:
            try:
                process = subprocess.Popen(
                    argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL, start_new_session=True,
                )
            except OSError as exc:
                raise StudioError(f"Cannot start {argv[0]!r}: {exc}") from exc
            os.set_blocking(process.stdout.fileno(), False)
            selector.register(process.stdout, selectors.EVENT_READ)
            written = 0
            while True:
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    reason = "timeout"
                    break
                events = selector.select(timeout=min(0.1, remaining))
                stop = False
                for key, _ in events:
                    try:
                        chunk = os.read(key.fd, 65536)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    room = max_log_bytes - written
                    output.write(chunk[:room])
                    written += min(room, len(chunk))
                    if len(chunk) > room:
                        reason = "log_limit"
                        stop = True
                        break
                if stop or (process.poll() is not None and not events):
                    break
                if process.poll() is not None and not selector.get_map():
                    break
    finally:
        if process is not None:
            # A wrapper may exit while its helpers remain alive. End the entire owned group.
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            process.stdout.close()
    return {
        "exit_code": process.returncode,
        "reason": reason,
        "seconds": round(time.monotonic() - started, 3),
        "log": str(log),
    }
