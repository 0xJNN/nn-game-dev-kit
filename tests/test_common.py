import math
import os
import unittest

from helpers import ProjectTest
from pipeline.common import StudioError, atomic_json, load_json, money, project_path, resource_lock, usd


class CommonTests(ProjectTest):
    def test_exact_microdollars(self):
        self.assertEqual(money("0.000001"), 1)
        self.assertEqual(money("1.001"), 1001000)
        self.assertEqual(usd(1001000), "1.001000")

    def test_invalid_money(self):
        for value in ["NaN", "Infinity", -1, "0.0000001", "invalid", True, math.inf]:
            with self.subTest(value=value), self.assertRaises(StudioError):
                money(value)

    def test_rejects_escaping_paths(self):
        for value in ["../elsewhere", "/etc/passwd", "", "a/../../b"]:
            with self.subTest(value=value), self.assertRaises(StudioError):
                project_path(value, self.root)

    def test_rejects_symlink_escape(self):
        (self.root / "escape").symlink_to(self.root.parent, target_is_directory=True)
        with self.assertRaises(StudioError):
            project_path("escape/secret.txt", self.root)

    def test_atomic_json_does_not_leave_partial_files(self):
        path = self.root / "state.json"
        atomic_json(path, {"status": "first"})
        atomic_json(path, {"status": "second"})
        self.assertEqual(load_json(path), {"status": "second"})
        self.assertEqual(list(self.root.glob(".pending-*")), [])

    def test_atomic_json_rejects_nonfinite_values_without_overwriting(self):
        path = self.root / "state.json"
        atomic_json(path, {"valid": True})
        with self.assertRaises(ValueError):
            atomic_json(path, {"bad": float("nan")})
        self.assertEqual(load_json(path), {"valid": True})

    @unittest.skipIf(os.name != "posix", "POSIX locks")
    def test_shared_resource_has_one_owner(self):
        with resource_lock("editor", self.root):
            with self.assertRaises(StudioError):
                with resource_lock("editor", self.root):
                    self.fail("Second owner acquired editor")
        with resource_lock("editor", self.root):
            pass
