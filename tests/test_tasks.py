from helpers import ProjectTest
from pipeline.common import StudioError, load_json
from pipeline.tasks import read_contract, run_task, task_context


class TaskTests(ProjectTest):
    def test_dry_run_never_executes(self):
        result = run_task(self.contract(), root=self.root)
        self.assertEqual(result["status"], "dry_run")
        self.assertFalse((self.root / "result.txt").exists())

    def test_success_is_machine_verified_not_human_approved(self):
        result = run_task(self.contract(), execute=True, root=self.root)
        self.assertEqual(result["status"], "machine_verified")
        self.assertEqual(result["human_approval"], "pending")
        self.assertEqual(len(result["commands"]), 2)
        self.assertEqual(load_json(self.root / result["evidence"] / "report.json")["status"], "machine_verified")

    def test_failed_verification_stops_after_attempt_limit(self):
        contract = self.contract(verification=[{"name": "fail", "argv": ["{python}", "-c", "raise SystemExit(1)"]}])
        result = run_task(contract, execute=True, root=self.root)
        self.assertEqual(result["status"], "attempts_exhausted")
        self.assertEqual(len(result["commands"]), 2)

    def test_deadline_kills_command(self):
        contract = self.contract(
            limits={"deadline_seconds": 1, "command_timeout_seconds": 1,
                    "max_attempts": 3, "budget_usd": "0"},
            steps=[{"name": "slow", "argv": ["{python}", "-c", "import time; time.sleep(30)"]}],
        )
        result = run_task(contract, execute=True, root=self.root)
        self.assertEqual(result["status"], "deadline_exceeded")
        self.assertLess(result["seconds"], 5)
        self.assertEqual(len(result["commands"]), 1)

    def test_write_boundary_failure_is_reported_without_deleting_work(self):
        contract = self.contract(allowed_writes=[])
        result = run_task(contract, execute=True, root=self.root)
        self.assertEqual(result["status"], "write_boundary_violated")
        self.assertEqual(result["unexpected_writes"], ["result.txt"])
        self.assertTrue((self.root / "result.txt").exists())

    def test_missing_binary_leaves_error_journal(self):
        contract = self.contract(steps=[{"name": "missing", "argv": ["/not/a/real/binary"]}])
        with self.assertRaises(StudioError):
            run_task(contract, execute=True, root=self.root)
        report = next((self.root / ".studio/runs").glob("*/report.json"))
        self.assertEqual(load_json(report)["status"], "error")

    def test_context_is_small_and_explicit(self):
        (self.root / "brief.md").write_text("Only the relevant brief")
        contract = self.contract(inputs=["brief.md"])
        text = task_context(read_contract(contract, self.root), self.root)
        self.assertIn("Only the relevant brief", text)
        self.assertLess(len(text), 20000)

    def test_large_context_is_refused_not_silently_truncated(self):
        (self.root / "brief.md").write_text("x" * 21000)
        contract = self.contract(inputs=["brief.md"])
        with self.assertRaises(StudioError):
            task_context(read_contract(contract, self.root), self.root)

    def test_secret_context_is_refused(self):
        contract = self.contract(inputs=[".env"])
        with self.assertRaises(StudioError):
            read_contract(contract, self.root)

    def test_protected_or_broad_write_paths_are_refused(self):
        for path in [".", ".git/config", "../escape", ".studio/ledger.sqlite3"]:
            with self.subTest(path=path):
                contract = self.contract(allowed_writes=[path])
                with self.assertRaises(StudioError):
                    read_contract(contract, self.root)

    def test_invalid_contracts_fail_closed(self):
        for override in [
            {"verification": []}, {"id": "Bad ID"}, {"goal": ""},
            {"acceptance": []}, {"typo": True}, {"steps": [{"name": "bad", "argv": "echo unsafe"}]},
            {"limits": {"deadline_seconds": 1, "command_timeout_seconds": 2, "max_attempts": 1, "budget_usd": "0"}},
            {"limits": {"deadline_seconds": 10, "command_timeout_seconds": 5, "max_attempts": 100, "budget_usd": "0"}},
            {"limits": {"deadline_seconds": 10, "command_timeout_seconds": 5, "max_attempts": 1, "budget_usd": "6"}},
        ]:
            with self.subTest(override=override), self.assertRaises(StudioError):
                read_contract(self.contract(**override), self.root)
