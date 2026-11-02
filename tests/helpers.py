import shutil
import tempfile
import unittest
from pathlib import Path

from pipeline.common import ROOT, atomic_json


class ProjectTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="novanode-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        shutil.copy(ROOT / "studio.toml", self.root / "studio.toml")

    def contract(self, **overrides):
        task = {
            "id": "example", "goal": "Test a bounded local task", "inputs": [],
            "allowed_writes": ["result.txt"], "acceptance": ["verification succeeds"],
            "limits": {"deadline_seconds": 10, "command_timeout_seconds": 5,
                       "max_attempts": 1, "budget_usd": "0"},
            "steps": [{"name": "implement", "argv": ["{python}", "-c",
                       "from pathlib import Path; Path('result.txt').write_text('ok')"]}],
            "verification": [{"name": "verify", "argv": ["{python}", "-c",
                              "from pathlib import Path; assert Path('result.txt').read_text() == 'ok'"]}],
        }
        task.update(overrides)
        path = self.root / "task.json"
        atomic_json(path, task)
        return path
