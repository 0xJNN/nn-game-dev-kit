from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .common import StudioError, money, usd, utc_now


class Ledger:
    """Durable reservations. An unknown/abandoned paid job keeps its full hold."""

    def __init__(self, path: Path, total_usd, per_task_usd):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.total = money(total_usd)
        self.per_task = money(per_task_usd)
        self.db = sqlite3.connect(path, timeout=10, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                key TEXT PRIMARY KEY, task TEXT NOT NULL, provider TEXT NOT NULL,
                operation TEXT NOT NULL, reserved INTEGER NOT NULL,
                actual INTEGER, provider_job_id TEXT, outcome TEXT,
                receipt TEXT, created_at TEXT NOT NULL, settled_at TEXT, usage_json TEXT
            )
        """)
        columns = {row["name"] for row in self.db.execute("PRAGMA table_info(jobs)")}
        if "usage_json" not in columns:
            self.db.execute("ALTER TABLE jobs ADD COLUMN usage_json TEXT")
        self.db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS provider_job_identity "
            "ON jobs(provider,provider_job_id) WHERE provider_job_id IS NOT NULL"
        )

    def close(self):
        self.db.close()

    @staticmethod
    def describe(row, created=False):
        result = dict(row)
        result["reserved_usd"] = usd(result.pop("reserved"))
        actual = result.pop("actual")
        result["actual_usd"] = None if actual is None else usd(actual)
        usage = result.pop("usage_json")
        result["usage"] = json.loads(usage) if usage is not None else None
        result["created"] = created
        result["action"] = (
            "complete" if actual is not None else
            "submit" if created else
            "resume" if result["provider_job_id"] else "reconcile"
        )
        return result

    def reserve(self, key: str, task: str, provider: str, operation: str, max_cost,
                task_cap=None) -> dict:
        for value in (key, task, provider, operation):
            if not isinstance(value, str) or not value.strip() or len(value) > 250:
                raise StudioError("Job identifiers must be nonempty strings <= 250 characters")
        amount = money(max_cost)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            existing = self.db.execute("SELECT * FROM jobs WHERE key=?", (key,)).fetchone()
            if existing:
                if (existing["task"], existing["provider"], existing["operation"],
                    existing["reserved"]) != (task, provider, operation, amount):
                    raise StudioError("Idempotency key already belongs to a different request")
                self.db.execute("COMMIT")
                return self.describe(existing)
            total = self.db.execute(
                "SELECT COALESCE(SUM(COALESCE(actual, reserved)),0) FROM jobs"
            ).fetchone()[0]
            task_total = self.db.execute(
                "SELECT COALESCE(SUM(COALESCE(actual, reserved)),0) FROM jobs WHERE task=?",
                (task,),
            ).fetchone()[0]
            cap = min(self.per_task, money(task_cap)) if task_cap is not None else self.per_task
            overrun = self.db.execute(
                "SELECT 1 FROM jobs WHERE actual > reserved LIMIT 1"
            ).fetchone()
            if overrun or total + amount > self.total or task_total + amount > cap:
                raise StudioError("Budget exhausted: settled costs + outstanding holds exceed cap")
            self.db.execute(
                "INSERT INTO jobs(key,task,provider,operation,reserved,created_at) VALUES(?,?,?,?,?,?)",
                (key, task, provider, operation, amount, utc_now()),
            )
            row = self.db.execute("SELECT * FROM jobs WHERE key=?", (key,)).fetchone()
            self.db.execute("COMMIT")
            return self.describe(row, created=True)
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def attach(self, key: str, job_id: str) -> dict:
        if not job_id.strip():
            raise StudioError("Provider job ID cannot be empty")
        try:
            cursor = self.db.execute(
                "UPDATE jobs SET provider_job_id=? WHERE key=? AND actual IS NULL "
                "AND (provider_job_id IS NULL OR provider_job_id=?)", (job_id, key, job_id),
            )
        except sqlite3.IntegrityError as exc:
            raise StudioError("Provider job ID is already recorded under another key") from exc
        if not cursor.rowcount:
            raise StudioError("Job missing, settled, or already attached to a different provider ID")
        return self.get(key)

    def settle(self, key: str, actual_cost, outcome: str, receipt: str, usage=None) -> dict:
        if outcome not in {"accepted", "rejected", "failed", "cancelled"}:
            raise StudioError("Invalid settlement outcome")
        if not receipt.strip():
            raise StudioError("A provider receipt or local execution reference is required")
        actual = money(actual_cost)
        usage_fields = {"input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens"}
        if usage is not None and (
            not isinstance(usage, dict) or not usage or set(usage) - usage_fields
            or any(type(value) is not int or value < 0 for value in usage.values())
        ):
            raise StudioError("Usage must contain nonnegative integer token counts in known categories")
        usage_json = None if usage is None else json.dumps(usage, sort_keys=True)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute("SELECT * FROM jobs WHERE key=?", (key,)).fetchone()
            if row is None:
                raise StudioError("Unknown job")
            if row["actual"] is not None:
                if (row["actual"], row["outcome"], row["receipt"], row["usage_json"]) != (
                    actual, outcome, receipt, usage_json
                ):
                    raise StudioError("Settled receipts are immutable; conflicting settlement refused")
            else:
                # Record real overruns honestly; never discard an invoice to make a budget look good.
                self.db.execute(
                    "UPDATE jobs SET actual=?,outcome=?,receipt=?,settled_at=?,usage_json=? WHERE key=?",
                    (actual, outcome, receipt, utc_now(), usage_json, key),
                )
            self.db.execute("COMMIT")
            return self.get(key)
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def get(self, key: str) -> dict:
        row = self.db.execute("SELECT * FROM jobs WHERE key=?", (key,)).fetchone()
        if row is None:
            raise StudioError("Unknown job")
        return self.describe(row)

    def report(self) -> dict:
        rows = self.db.execute("SELECT * FROM jobs ORDER BY created_at,key").fetchall()
        settled = sum(row["actual"] or 0 for row in rows)
        held = sum(row["reserved"] for row in rows if row["actual"] is None)
        usage = [json.loads(row["usage_json"]) if row["usage_json"] is not None else {}
                 for row in rows]
        token_totals = {}
        for category in ("input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens"):
            recorded = [entry[category] for entry in usage if category in entry]
            token_totals[category] = {
                "recorded_total": sum(recorded) if recorded else None,
                "jobs_not_recorded": len(rows) - len(recorded),
            }
        return {
            "settled_usd": usd(settled), "held_usd": usd(held),
            "remaining_usd": usd(self.total - settled - held),
            "budget_breached": settled + held > self.total or any(
                row["actual"] is not None and row["actual"] > row["reserved"] for row in rows
            ),
            "token_usage": token_totals,
            "accepted_jobs": sum(row["outcome"] == "accepted" for row in rows),
            "rejected_jobs": sum(row["outcome"] == "rejected" for row in rows),
            "jobs": [self.describe(row) for row in rows],
        }
