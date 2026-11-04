from unittest.mock import patch

from helpers import ProjectTest
from pipeline.common import StudioError, load_json
from pipeline.process import run_process
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

    def assert_unknown_stops(self, outcome, phase="steps", stop_reason=None):
        commands = {
            name: [{"name": f"{name}-{index}", "argv": ["NOT-EXECUTED"]} for index in (1, 2)]
            for name in ("steps", "verification")
        }
        contract = self.contract(
            limits={"deadline_seconds": 10, "command_timeout_seconds": 1,
                    "max_attempts": 3, "budget_usd": "0"},
            **commands,
        )
        expected_calls = 1 if phase == "steps" else 3

        def simulate(argv, cwd, timeout, log, env):
            log.write_text("Preserved command evidence\n")
            response = outcome if command.call_count == expected_calls else {
                "reason": "completed", "exit_code": 0, "seconds": 0.01,
            }
            return {**response, "log": str(log)}

        with patch("pipeline.tasks.run_process", side_effect=simulate) as command:
            result = run_task(contract, execute=True, root=self.root)
        self.assertEqual(command.call_count, expected_calls)
        self.assertEqual(result["status"], "outcome_unknown")
        self.assertEqual(result["stop_reason"], stop_reason or outcome["reason"])
        self.assertTrue(result["reconciliation_required"])
        self.assertEqual(result["human_approval"], "pending")
        self.assertEqual(len(result["commands"]), expected_calls)
        self.assertTrue(all(row["attempt"] == 1 for row in result["commands"]))
        record = result["commands"][-1]
        self.assertEqual(record["phase"], phase)
        self.assertEqual(record["reason"], outcome["reason"])
        self.assertEqual(record["exit_code"], outcome["exit_code"])
        self.assertEqual((self.root / record["log"]).read_text(), "Preserved command evidence\n")
        self.assertEqual(load_json(self.root / result["evidence"] / "report.json"), result)

    def test_timeout_and_log_limit_never_retry_in_either_phase(self):
        for phase in ("steps", "verification"):
            for reason in ("timeout", "log_limit"):
                for exit_code in (-15, 0):
                    with self.subTest(phase=phase, reason=reason, exit_code=exit_code):
                        self.assert_unknown_stops(
                            {"reason": reason, "exit_code": exit_code, "seconds": 0.01}, phase,
                        )

    def test_interrupted_and_unrecognized_results_never_retry(self):
        for reason in ("interrupted", "unexpected_transport_state"):
            with self.subTest(reason=reason):
                self.assert_unknown_stops({"reason": reason, "exit_code": None, "seconds": 0.01})

    def test_signal_or_missing_exit_status_never_retry(self):
        for exit_code, reason in ((-9, "signal"), (None, "unknown_exit_code")):
            with self.subTest(exit_code=exit_code):
                self.assert_unknown_stops(
                    {"reason": "completed", "exit_code": exit_code, "seconds": 0.01},
                    stop_reason=reason,
                )

    def test_known_nonzero_exit_can_retry_the_deterministic_package(self):
        contract = self.contract(
            limits={"deadline_seconds": 10, "command_timeout_seconds": 1,
                    "max_attempts": 2, "budget_usd": "0"},
        )
        outcomes = [
            {"reason": "completed", "exit_code": 0, "seconds": 0.01},
            {"reason": "completed", "exit_code": 1, "seconds": 0.01},
            {"reason": "completed", "exit_code": 0, "seconds": 0.01},
            {"reason": "completed", "exit_code": 0, "seconds": 0.01},
        ]
        with patch("pipeline.tasks.run_process", side_effect=outcomes) as command:
            result = run_task(contract, execute=True, root=self.root)
        self.assertEqual(command.call_count, 4)
        self.assertEqual(result["status"], "machine_verified")
        self.assertEqual([row["attempt"] for row in result["commands"]], [1, 1, 2, 2])
        self.assertFalse(result.get("reconciliation_required", False))
        self.assertEqual(result["human_approval"], "pending")

    def test_real_command_timeout_stops_before_another_attempt(self):
        contract = self.contract(
            limits={"deadline_seconds": 10, "command_timeout_seconds": 1,
                    "max_attempts": 3, "budget_usd": "0"},
            steps=[{"name": "slow", "argv": ["{python}", "-c",
                   "from pathlib import Path; import time; "
                   "p = Path('result.txt'); p.write_text(p.read_text() + 'x' if p.exists() else 'x'); "
                   "print('started', flush=True); time.sleep(30)"]}],
        )
        result = run_task(contract, execute=True, root=self.root)
        self.assertEqual(result["status"], "outcome_unknown")
        self.assertEqual(result["stop_reason"], "timeout")
        self.assertTrue(result["reconciliation_required"])
        self.assertEqual(len(result["commands"]), 1)
        self.assertEqual((self.root / "result.txt").read_text(), "x")
        self.assertIn("started", (self.root / result["commands"][0]["log"]).read_text())
        self.assertLess(result["seconds"], 5)

    def test_real_log_limit_stops_and_preserves_bounded_output(self):
        contract = self.contract(
            limits={"deadline_seconds": 10, "command_timeout_seconds": 2,
                    "max_attempts": 3, "budget_usd": "0"},
            steps=[{"name": "noisy", "argv": ["{python}", "-c",
                   "from pathlib import Path; import time; "
                   "p = Path('result.txt'); p.write_text(p.read_text() + 'x' if p.exists() else 'x'); "
                   "print('x' * 1024, flush=True); time.sleep(30)"]}],
        )

        def bounded(*args):
            return run_process(*args, max_log_bytes=64)

        with patch("pipeline.tasks.run_process", side_effect=bounded) as command:
            result = run_task(contract, execute=True, root=self.root)
        self.assertEqual(command.call_count, 1)
        self.assertEqual(result["status"], "outcome_unknown")
        self.assertEqual(result["stop_reason"], "log_limit")
        self.assertTrue(result["reconciliation_required"])
        self.assertEqual((self.root / "result.txt").read_text(), "x")
        self.assertEqual((self.root / result["commands"][0]["log"]).stat().st_size, 64)
        self.assertLess(result["seconds"], 5)

    def test_unknown_outcome_still_audits_and_preserves_unexpected_writes(self):
        contract = self.contract(
            allowed_writes=[],
            limits={"deadline_seconds": 10, "command_timeout_seconds": 1,
                    "max_attempts": 3, "budget_usd": "0"},
        )

        def timeout(*args):
            (self.root / "result.txt").write_text("Preserve this partial result")
            return {"reason": "timeout", "exit_code": -15, "seconds": 0.01}

        with patch("pipeline.tasks.run_process", side_effect=timeout) as command:
            result = run_task(contract, execute=True, root=self.root)
        self.assertEqual(command.call_count, 1)
        self.assertEqual(result["status"], "write_boundary_violated")
        self.assertEqual(result["unexpected_writes"], ["result.txt"])
        self.assertTrue(result["reconciliation_required"])
        self.assertEqual(result["stop_reason"], "timeout")
        self.assertEqual((self.root / "result.txt").read_text(), "Preserve this partial result")

    def test_keyboard_interrupt_journals_identity_logs_and_write_audit(self):
        contract = self.contract(allowed_writes=[])

        def interrupt(argv, cwd, timeout, log, env):
            log.write_text("Partial output before interruption\n")
            (self.root / "result.txt").write_text("Do not delete interrupted work")
            raise KeyboardInterrupt

        with patch("pipeline.tasks.run_process", side_effect=interrupt) as command:
            with self.assertRaises(KeyboardInterrupt):
                run_task(contract, execute=True, root=self.root)
        self.assertEqual(command.call_count, 1)
        report = load_json(next((self.root / ".studio/runs").glob("*/report.json")))
        self.assertEqual(report["status"], "write_boundary_violated")
        self.assertEqual(report["stop_reason"], "interrupted")
        self.assertTrue(report["reconciliation_required"])
        self.assertEqual(report["unexpected_writes"], ["result.txt"])
        self.assertEqual(report["commands"][0]["reason"], "interrupted")
        self.assertEqual(report["commands"][0]["attempt"], 1)
        self.assertEqual(report["commands"][0]["phase"], "steps")
        self.assertTrue(report["commands"][0]["argv"])
        self.assertIn("Partial output", (self.root / report["commands"][0]["log"]).read_text())
        self.assertTrue((self.root / "result.txt").exists())

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
