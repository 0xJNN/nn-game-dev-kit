from concurrent.futures import ThreadPoolExecutor

from helpers import ProjectTest
from pipeline.common import StudioError
from pipeline.ledger import Ledger


class LedgerTests(ProjectTest):
    def ledger(self, total="10", per_task="5"):
        ledger = Ledger(self.root / "ledger.sqlite3", total, per_task)
        self.addCleanup(ledger.close)
        return ledger

    def test_reservation_is_idempotent(self):
        ledger = self.ledger()
        first = ledger.reserve("key", "task", "provider", "mesh", "1")
        second = ledger.reserve("key", "task", "provider", "mesh", "1")
        self.assertEqual(first["action"], "submit")
        self.assertEqual(second["action"], "reconcile")
        self.assertEqual(ledger.report()["held_usd"], "1.000000")

    def test_key_cannot_change_request(self):
        ledger = self.ledger()
        ledger.reserve("key", "task", "provider", "mesh", "1")
        with self.assertRaises(StudioError):
            ledger.reserve("key", "task", "provider", "different", "1")

    def test_provider_id_resumes_instead_of_resubmitting(self):
        ledger = self.ledger()
        ledger.reserve("key", "task", "provider", "mesh", "1")
        ledger.attach("key", "external-job-123")
        self.assertEqual(ledger.reserve("key", "task", "provider", "mesh", "1")["action"], "resume")
        with self.assertRaises(StudioError):
            ledger.attach("key", "different-job")

    def test_provider_job_cannot_be_counted_under_two_keys(self):
        ledger = self.ledger()
        ledger.reserve("one", "task", "provider", "mesh", "1")
        ledger.reserve("two", "task", "provider", "mesh", "1")
        ledger.attach("one", "job-123")
        with self.assertRaises(StudioError):
            ledger.attach("two", "job-123")

    def test_settlement_is_immutable_and_idempotent(self):
        ledger = self.ledger()
        ledger.reserve("key", "task", "provider", "mesh", "2")
        ledger.settle("key", "1.25", "accepted", "receipt-1")
        ledger.settle("key", "1.25", "accepted", "receipt-1")
        self.assertEqual(ledger.get("key")["action"], "complete")
        self.assertEqual(ledger.report()["held_usd"], "0.000000")
        self.assertEqual(ledger.report()["remaining_usd"], "8.750000")
        with self.assertRaises(StudioError):
            ledger.settle("key", "0", "accepted", "receipt-1")

    def test_ambiguous_failure_keeps_hold(self):
        ledger = self.ledger(total="2")
        ledger.reserve("lost", "task", "provider", "mesh", "2")
        ledger.close()
        # Remove the cleanup for the already-closed connection (close is idempotent).
        reopened = self.ledger(total="2")
        with self.assertRaises(StudioError):
            reopened.reserve("retry", "task", "provider", "mesh", "0.01")

    def test_task_budget_includes_all_attempts(self):
        ledger = self.ledger()
        ledger.reserve("one", "task", "provider", "mesh", "3")
        with self.assertRaises(StudioError):
            ledger.reserve("two", "task", "provider", "mesh", "3")

    def test_contract_cap_can_only_reduce_studio_cap(self):
        ledger = self.ledger()
        with self.assertRaises(StudioError):
            ledger.reserve("one", "task", "provider", "mesh", "2", task_cap="1")
        with self.assertRaises(StudioError):
            ledger.reserve("two", "task", "provider", "mesh", "6", task_cap="100")

    def test_actual_overrun_is_recorded_and_freezes_new_spend(self):
        ledger = self.ledger()
        ledger.reserve("one", "task", "provider", "mesh", "1")
        ledger.settle("one", "2", "rejected", "real-invoice")
        self.assertTrue(ledger.report()["budget_breached"])
        self.assertEqual(ledger.report()["settled_usd"], "2.000000")
        with self.assertRaises(StudioError):
            ledger.reserve("two", "other-task", "provider", "mesh", "0.01")

    def test_settlement_requires_evidence(self):
        ledger = self.ledger()
        ledger.reserve("one", "task", "provider", "mesh", "1")
        with self.assertRaises(StudioError):
            ledger.settle("one", "0", "failed", "")

    def test_usage_separates_cached_tokens_and_preserves_unknowns(self):
        ledger = self.ledger()
        ledger.reserve("one", "task", "provider", "code", "1")
        ledger.reserve("two", "task", "provider", "code", "1")
        ledger.settle("one", "0.1", "accepted", "receipt", usage={
            "input_tokens": 100, "cache_read_tokens": 200, "output_tokens": 50,
        })
        usage = ledger.report()["token_usage"]
        self.assertEqual(usage["input_tokens"], {"recorded_total": 100, "jobs_not_recorded": 1})
        self.assertEqual(usage["cache_read_tokens"]["recorded_total"], 200)
        self.assertIsNone(usage["cache_write_tokens"]["recorded_total"])

    def test_usage_rejects_negative_and_boolean_counts(self):
        ledger = self.ledger()
        ledger.reserve("one", "task", "provider", "code", "1")
        for usage in [{"input_tokens": -1}, {"output_tokens": True}, {"unknown": 1}, {}]:
            with self.subTest(usage=usage), self.assertRaises(StudioError):
                ledger.settle("one", "0", "failed", "receipt", usage=usage)

    def test_concurrent_reservations_cannot_oversubscribe(self):
        ledger = self.ledger(total="3", per_task="3")

        def reserve(index):
            other = Ledger(self.root / "ledger.sqlite3", "3", "3")
            try:
                other.reserve(f"key-{index}", f"task-{index}", "provider", "mesh", "1")
                return True
            except StudioError:
                return False
            finally:
                other.close()

        with ThreadPoolExecutor(max_workers=8) as executor:
            accepted = list(executor.map(reserve, range(8)))
        self.assertEqual(sum(accepted), 3)
        self.assertEqual(ledger.report()["remaining_usd"], "0.000000")
