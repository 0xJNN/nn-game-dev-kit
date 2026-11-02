from helpers import ProjectTest
from pipeline.common import atomic_json
from scripts.verify_evidence import verify


class EvidenceTests(ProjectTest):
    def test_genuine_check_report_is_accepted(self):
        path = self.root / "evidence.json"
        atomic_json(path, {"status": "passed", "human_approval": "pending",
                           "checks": [{"name": "door", "passed": True}]})
        verify(path, 1)

    def test_contradictory_failed_duplicate_and_empty_reports_are_refused(self):
        for checks in [[], [{"name": "door", "passed": False}],
                       [{"name": "door", "passed": True}, {"name": "door", "passed": True}]]:
            with self.subTest(checks=checks):
                path = self.root / "evidence.json"
                atomic_json(path, {"status": "passed", "human_approval": "pending", "checks": checks})
                with self.assertRaises(ValueError):
                    verify(path, 1)

    def test_fixture_cannot_grant_human_approval(self):
        path = self.root / "evidence.json"
        atomic_json(path, {"status": "passed", "human_approval": "approved",
                           "checks": [{"name": "door", "passed": True}]})
        with self.assertRaises(ValueError):
            verify(path, 1)
