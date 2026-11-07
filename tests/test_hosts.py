import copy
import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from pipeline import hosts
from pipeline.common import StudioError

NOW = datetime(2026, 11, 7, 12, tzinfo=timezone.utc)


def snapshot(node, role):
    return {
        "schema_version": 1, "captured_at": NOW.isoformat(), "node": node,
        "role": role, "hostname": node,
        "system": {"platform": "Linux", "distribution": "fedora", "cpu_model": "CPU",
                   "logical_cpus": 16, "ram_total_mib": 63500, "disk_free_mib": 80000},
        "gpu": {"status": "observed", "devices": [{
            "uuid": f"GPU-{node}", "name": "NVIDIA GeForce RTX 3090", "total_mib": 24576,
            "used_mib": 20000, "free_mib": 4500, "driver_version": "test-driver",
        }]},
    }


class HostTests(unittest.TestCase):
    def setUp(self):
        self.pair = [snapshot("ubuntu", "production"), snapshot("fedora", "inference")]

    def codes(self, pair=None):
        return {issue["code"] for issue in hosts.compare(
            self.pair if pair is None else pair, now=NOW)["issues"]}

    def test_complete_inventory_cannot_promote_workloads_or_human_approval(self):
        for item in self.pair:
            item.update(pipeline_verified=True, human_approval="approved", status="ready")
        result = hosts.compare(self.pair, now=NOW)
        self.assertEqual(result["status"], "inventory_complete")
        self.assertFalse(result["pipeline_verified"])
        self.assertEqual(result["human_approval"], "pending")
        self.assertIn("resource_ownership_and_live_vram", result["pending_gates"])
        self.assertIn("exact_model_runtime_and_tool_transport", result["pending_gates"])

    def test_renaming_snapshot_cannot_turn_one_gpu_into_two_pcs(self):
        self.pair[1]["gpu"] = copy.deepcopy(self.pair[0]["gpu"])
        self.assertIn("duplicate_gpu_identity", self.codes())

    def test_duplicate_roles_nodes_and_hosts_are_reported(self):
        self.assertTrue({"duplicate_role", "duplicate_node", "same_hostname_review_required"}
                        <= self.codes([self.pair[0], self.pair[0]]))
        self.assertIn("exactly_two_snapshots_required", self.codes([self.pair[0]]))

    def test_old_future_naive_and_invalid_timestamps_are_not_current_evidence(self):
        for value, code in [
            ((NOW - timedelta(days=2)).isoformat(), "stale_or_future_snapshot"),
            ((NOW + timedelta(minutes=2)).isoformat(), "stale_or_future_snapshot"),
            ("2026-11-07T12:00:00", "invalid_timestamp"),
            (None, "invalid_timestamp"), ([], "invalid_timestamp"),
        ]:
            with self.subTest(value=value):
                self.pair[0]["captured_at"] = value
                self.assertIn(code, self.codes())

    def test_unknown_gpu_does_not_become_free_or_absent_gpu(self):
        self.pair[0]["gpu"] = {"status": "unknown", "reason": "timeout", "devices": []}
        self.assertIn("gpu_observation_unknown", self.codes())

    def test_missing_or_false_hardware_metrics_fail_closed(self):
        for field, value in [("ram_total_mib", True), ("ram_total_mib", 32000),
                             ("disk_free_mib", None), ("logical_cpus", 0),
                             ("cpu_model", ""), ("platform", "Windows")]:
            with self.subTest(field=field, value=value):
                pair = copy.deepcopy(self.pair)
                pair[0]["system"][field] = value
                self.assertEqual(hosts.compare(pair, now=NOW)["status"], "blocked")
        for value in [None, True, -1, float("nan"), "24576"]:
            with self.subTest(value=value):
                pair = copy.deepcopy(self.pair)
                pair[0]["gpu"]["devices"][0]["total_mib"] = value
                self.assertIn("gpu_memory_unknown_or_invalid", self.codes(pair))

    def test_malformed_shapes_do_not_crash_or_pass(self):
        for field, value in [("schema_version", True), ("node", []), ("role", {}),
                             ("hostname", []), ("system", []), ("gpu", []),
                             ("gpu", {"status": "observed", "devices": [None]})]:
            with self.subTest(field=field):
                pair = copy.deepcopy(self.pair)
                pair[0][field] = value
                self.assertEqual(hosts.compare(pair, now=NOW)["status"], "blocked")

    def test_gpu_metrics_preserve_reported_free_memory_not_total_minus_used(self):
        devices = hosts.parse_gpus("GPU-one, NVIDIA RTX 3090, 24576, 20000, 4500, 570.1\n")
        self.assertEqual(devices[0]["free_mib"], 4500)
        self.assertNotEqual(devices[0]["free_mib"], 24576 - 20000)
        for text in ["", "GPU-x, GPU, 24576, N/A, 24000, 570", "bad, GPU, 24, 0, 24, 570",
                     "GPU-x, GPU, 24, 20, 20, 570", "GPU-x, GPU, -1, 0, 0, 570"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                hosts.parse_gpus(text)

    def test_probe_only_runs_fixed_readonly_query_and_does_not_log_stderr(self):
        result = subprocess.CompletedProcess([], 9, stdout="sensitive diagnostic", stderr=None)
        with patch.object(hosts.subprocess, "run", return_value=result) as run:
            observed = hosts.probe_gpus("/usr/bin/nvidia-smi")
        self.assertEqual(observed["status"], "unknown")
        self.assertNotIn("sensitive", json.dumps(observed))
        args, kwargs = run.call_args
        self.assertEqual(args[0], ["/usr/bin/nvidia-smi", f"--query-gpu={hosts.GPU_FIELDS}",
                                  "--format=csv,noheader,nounits"])
        self.assertEqual(kwargs["timeout"], 5)
        self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
        self.assertNotIn("shell", kwargs)

    def test_timeout_is_unknown_without_retry(self):
        with patch.object(hosts.subprocess, "run", side_effect=subprocess.TimeoutExpired("x", 5)) as run:
            observed = hosts.probe_gpus("nvidia-smi")
        self.assertEqual(observed["reason"], "nvidia_smi_timeout")
        run.assert_called_once()
        with patch.object(hosts.subprocess, "run") as run:
            self.assertEqual(hosts.probe_gpus(None)["status"], "unknown")
        run.assert_not_called()

    def test_inventory_locates_tools_without_running_them_or_writing(self):
        with patch.object(hosts.shutil, "which", return_value=None), \
                patch.object(hosts.subprocess, "run") as run, \
                patch.object(Path, "write_text") as write:
            report = hosts.inventory("test-node", "inference")
        self.assertFalse(report["pipeline_verified"])
        self.assertEqual(report["gpu"]["reason"], "nvidia_smi_not_found")
        self.assertEqual(set(report["tools_found_not_qualified"]), set(hosts.TOOLS))
        run.assert_not_called()
        write.assert_not_called()

    def test_comparison_cli_reports_missing_snapshot_without_traceback(self):
        out = io.StringIO()
        with redirect_stdout(out):
            result = hosts.main(["compare", "/nonexistent/ubuntu.json", "/nonexistent/fedora.json"])
        self.assertEqual(result, 2)
        self.assertEqual(json.loads(out.getvalue())["status"], "error")

    def test_snapshot_reader_rejects_symlinks_oversized_and_malformed_files(self):
        directory = hosts.ROOT / ".studio/bench/host-tests"
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=directory) as temporary:
            path = Path(temporary) / "snapshot.json"
            path.write_text(json.dumps(self.pair[0]), encoding="utf-8-sig")
            self.assertEqual(hosts.read_snapshot(path)["node"], "ubuntu")
            link = Path(temporary) / "link.json"
            link.symlink_to(path)
            with self.assertRaises(StudioError):
                hosts.read_snapshot(link)
            for data in ["[]", "{bad json", " " * (hosts.MAX_SNAPSHOT_BYTES + 1)]:
                path.write_text(data, encoding="utf-8")
                with self.subTest(data_length=len(data)), self.assertRaises(StudioError):
                    hosts.read_snapshot(path)


if __name__ == "__main__":
    unittest.main()
