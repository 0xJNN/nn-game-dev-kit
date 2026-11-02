from __future__ import annotations

import json
import os
import tempfile
import tomllib
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class StudioError(Exception):
    """An actionable validation or workflow error."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StudioError(f"Cannot read JSON {path}: {exc}") from exc


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def config(root: Path = ROOT) -> dict:
    with (root / "studio.toml").open("rb") as stream:
        return tomllib.load(stream)


def project_path(value: str, root: Path = ROOT) -> Path:
    """Resolve within the checkout, including symlinks; never accept absolute paths."""
    relative = Path(value)
    if not value or relative.is_absolute() or ".." in relative.parts:
        raise StudioError(f"Expected a project-relative path: {value!r}")
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise StudioError(f"Path escapes project: {value!r}")
    return path


def money(value) -> int:
    """Integer micro-dollars avoid floating-point budget drift."""
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0:
            raise ValueError()
        micros = number * 1_000_000
        if micros != micros.to_integral_value() or micros > 1_000_000_000_000:
            raise ValueError()
        return int(micros)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise StudioError("Cost must be finite, nonnegative USD with <= 6 decimals") from exc


def usd(micros: int) -> str:
    return format(Decimal(micros) / 1_000_000, ".6f")


@contextmanager
def resource_lock(name: str, root: Path = ROOT):
    """Cooperative, OS-released lock on macOS/Linux; not a security sandbox."""
    import fcntl

    directory = root / ".studio/locks"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / f"{name}.lock").open("a+") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise StudioError(f"Resource busy: {name}. Do not start a second owner.") from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)
